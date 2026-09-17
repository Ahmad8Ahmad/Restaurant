from django.db import models
from accounts.models import User
from restaurants.models import Restaurant, MenuItem
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='carts', verbose_name="المستخدم")
    session_key = models.CharField(max_length=40, null=True, blank=True, verbose_name="معرّف الجلسة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "سلة"
        verbose_name_plural = "السلال"
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(session_key__isnull=True),
                name='cart_uniq_authenticated_user',
            ),
            models.UniqueConstraint(
                fields=['session_key'],
                condition=models.Q(user__isnull=True, session_key__isnull=False),
                name='cart_uniq_guest_session',
            ),
        ]
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['session_key']),
        ]

    @classmethod
    def get_for_request(cls, request):
        if request.user.is_authenticated:
            return cls._get_or_create(user=request.user, session_key=None)
        if not request.session.session_key:
            request.session.save()
        return cls._get_or_create(user=None, session_key=request.session.session_key)

    @classmethod
    def _get_or_create(cls, **lookup):
        """get_or_create that never raises on legacy duplicate carts.

        The (user, session_key) pairing is enforced at the DB level by partial
        unique constraints, so the common path is race-safe. If duplicates
        somehow exist (e.g. created before the constraints were added), collapse
        them into the oldest cart instead of crashing."""
        try:
            cart, _ = cls.objects.get_or_create(**lookup)
        except cls.MultipleObjectsReturned:
            qs = cls.objects.filter(**lookup).order_by('id')
            keep = qs.first()
            for dup in qs.exclude(pk=keep.pk):
                for item in dup.items.all():
                    current = keep.items.filter(menu_item_id=item.menu_item_id).first()
                    if current is not None:
                        current.quantity = min(current.quantity + item.quantity, 99)
                        current.save(update_fields=['quantity'])
                    else:
                        item.cart = keep
                        item.save()
                dup.delete()
            cart = keep
        return cart

    def total_price(self):
        return sum(item.subtotal() for item in self.items.select_related('menu_item'))

    def total_quantity(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', verbose_name="السلة")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name="العنصر")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")

    class Meta:
        verbose_name = "عنصر سلة"
        verbose_name_plural = "عناصر السلة"
        indexes = [
            models.Index(fields=['cart']),
        ]

    def subtotal(self):
        price = self.menu_item.discount_price if self.menu_item.discount_price else self.menu_item.price
        return float(price) * self.quantity

    def unit_price(self):
        return float(self.menu_item.discount_price if self.menu_item.discount_price else self.menu_item.price)


class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'قيد الانتظار'),
        ('Confirmed', 'مؤكد'),
        ('Preparing', 'قيد التحضير'),
        ('Out for Delivery', 'في الطريق للتوصيل'),
        ('Delivered', 'تم التوصيل'),
        ('In Progress', 'قيد التنفيذ'),
        ('Completed', 'مكتمل'),
        ('Cancelled', 'ملغي'),
    ]
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='orders', null=True, blank=True, verbose_name="العميل")
    customer_name = models.CharField(max_length=255, blank=True, verbose_name="اسم العميل")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="رقم العميل")
    customer_email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='orders', verbose_name="المطعم")
    delivery_address = models.TextField(verbose_name="عنوان التوصيل")
    delivery_lat = models.FloatField(null=True, blank=True, verbose_name="خط عرض التوصيل")
    delivery_lng = models.FloatField(null=True, blank=True, verbose_name="خط طول التوصيل")
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="رسوم التوصيل")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="إجمالي السعر")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True, verbose_name="الحالة")
    customer_order_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="رقم الطلب للعميل")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        indexes = [
            models.Index(fields=['restaurant', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['customer', '-created_at']),
        ]

    def __str__(self):
        name = self.customer_name or (self.customer.username if self.customer else "Guest")
        return f"Order {self.id} by {name}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="الطلب")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name="العنصر")
    quantity = models.PositiveIntegerField(verbose_name="الكمية")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر")

    class Meta:
        verbose_name = "عنصر طلب"
        verbose_name_plural = "عناصر الطلبات"

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} for Order {self.order.id}"
    

class Review(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='reviews', verbose_name="المطعم")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="المستخدم")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="التقييم"
    )
    comment = models.TextField(verbose_name="التعليق", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تقييم"
        verbose_name_plural = "التقييمات"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['restaurant', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.restaurant.name} - {self.rating} Stars"


class Ticket(models.Model):
    code = models.CharField(max_length=20, unique=True, blank=True)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='ticket')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} - Order {self.order_id}"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip()
        if not self.code:
            import secrets
            import string
            alphabet = string.ascii_uppercase + string.digits
            self.code = ''.join(secrets.choice(alphabet) for _ in range(12))
        super().save(*args, **kwargs)
