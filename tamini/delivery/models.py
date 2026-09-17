import logging
from django.db import models
from django.conf import settings
from orders.models import Order
from tamini.utils import haversine_km

logger = logging.getLogger(__name__)

class DriverProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='driver_profile', verbose_name="المستخدم")
    is_approved = models.BooleanField(default=False, verbose_name="مقبول")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "ملف سائق"
        verbose_name_plural = "ملفات السائقين"

    def __str__(self):
        return f"{self.user.username} - {'Approved' if self.is_approved else 'Pending'}"

class Delivery(models.Model):
    STATUS_CHOICES = [
        ('searching', 'جاري البحث'),
        ('on_way', 'في الطريق'),
        ('picked_up', 'تم الاستلام'),
        ('delivered', 'تم التوصيل'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, verbose_name="الطلب")
    delivery_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="السائق")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='searching', db_index=True, verbose_name="الحالة")
    current_lat = models.FloatField(null=True, blank=True, verbose_name="خط العرض الحالي")
    current_lng = models.FloatField(null=True, blank=True, verbose_name="خط الطول الحالي")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, verbose_name="تاريخ التحديث")
    is_settled = models.BooleanField(default=False, db_index=True, verbose_name="تم التسوية")

    class Meta:
        verbose_name = "توصيلة"
        verbose_name_plural = "التوصيلات"
        indexes = [
            models.Index(fields=['delivery_person', 'status']),
            models.Index(fields=['delivery_person', '-updated_at']),
        ]

    def __str__(self):
        return f"Delivery for Order {self.order.id} - Status: {self.status}"
    
    
    def calculate_distance(self):
        try:
            restaurant = self.order.restaurant
            customer_lat = self.order.delivery_lat
            customer_lng = self.order.delivery_lng
            if not restaurant.latitude or not restaurant.longitude:
                return 0
            if not customer_lat or not customer_lng:
                return round(haversine_km(
                    float(restaurant.latitude), float(restaurant.longitude),
                    33.5138, 36.2765,
                ), 2)
            return round(haversine_km(
                float(restaurant.latitude), float(restaurant.longitude),
                float(customer_lat), float(customer_lng),
            ), 2)
        except Exception as e:
            logger.error(f"Error calculating distance: {e}", exc_info=True)
        return 0

    @property
    def delivery_fee(self):
        distance = self.calculate_distance()
        try:
            from support.models import SiteSettings
            site = SiteSettings.get_settings()
            base_fee = site.get('delivery_base_fee', 200)
            per_km_fee = site.get('delivery_per_km_fee', 1500)
        except Exception:
            base_fee = 200
            per_km_fee = 1500
        return round(base_fee + (distance * per_km_fee))

    @property
    def cached_distance(self):
        if not hasattr(self, '_dist_cache'):
            self._dist_cache = self.calculate_distance()
        return self._dist_cache

    @property
    def cached_fee(self):
        if not hasattr(self, '_fee_cache'):
            self._fee_cache = self.delivery_fee
        return self._fee_cache



