from django.db import models
from accounts.models import User
from restaurants.models import Restaurant, MenuItem
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='carts')
    session_key = models.CharField(max_length=40, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['session_key']),
        ]

    @classmethod
    def get_for_request(cls, request):
        if request.user.is_authenticated:
            cart, _ = cls.objects.get_or_create(user=request.user, session_key=None)
        else:
            if not request.session.session_key:
                request.session.save()
            cart, _ = cls.objects.get_or_create(user=None, session_key=request.session.session_key)
        return cart

    def total_price(self):
        return sum(item.subtotal() for item in self.items.select_related('menu_item'))

    def total_quantity(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
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
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Preparing', 'Preparing'),
        ('Out for Delivery', 'Out for Delivery'),
        ('Delivered', 'Delivered'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='orders', null=True, blank=True)
    customer_name = models.CharField(max_length=255, blank=True, verbose_name="اسم العميل")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="رقم العميل")
    customer_email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='orders')
    delivery_address = models.TextField()
    delivery_lat = models.FloatField(null=True, blank=True)
    delivery_lng = models.FloatField(null=True, blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True)
    customer_order_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="رقم الطلب للعميل")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        name = self.customer_name or (self.customer.username if self.customer else "Guest")
        return f"Order {self.id} by {name}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} for Order {self.order.id}"
    

class Review(models.Model):
    # ربط التقييم بالمطعم
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='reviews')
    # ربط التقييم بالمستخدم (الزبون)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # التقييم بالنجوم من 1 لـ 5
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="التقييم"
    )
    # نص التعليق
    comment = models.TextField(verbose_name="التعليق", blank=True, null=True)
    # التاريخ
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تقييم"
        verbose_name_plural = "التقييمات"
        ordering = ['-created_at']

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
