from django.db import models
from orders.models import Order


class Commission(models.Model):
    COMMISSION_TYPES = [
        ('restaurant', 'عمولة المطعم'),
        ('delivery', 'عمولة التوصيل'),
    ]
    commission_type = models.CharField(max_length=20, choices=COMMISSION_TYPES, verbose_name="نوع العمولة", db_index=True)
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, null=True, blank=True, related_name='commissions', verbose_name="الطلب")
    delivery = models.ForeignKey('delivery.Delivery', on_delete=models.CASCADE, null=True, blank=True, related_name='commissions', verbose_name="التوصيل")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    is_settled = models.BooleanField(default=False, verbose_name="تم التسوية", db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التسوية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عمولة"
        verbose_name_plural = "العمولات"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['commission_type', 'is_settled']),
            models.Index(fields=['order']),
        ]

    def __str__(self):
        return f"{self.get_commission_type_display()} - {self.amount} ل.س"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'قيد الانتظار'),
        ('Completed', 'مكتمل'),
        ('Failed', 'فشل'),
    ]
    METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('cash', 'نقداً'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment', verbose_name="الطلب")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True, verbose_name="الحالة")
    transaction_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="معرّف العملية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")
    payment_method = models.CharField(max_length=50, default='Card', db_index=True, verbose_name="طريقة الدفع")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash', db_index=True, verbose_name="الطريقة")
    provider_ref = models.CharField(max_length=255, blank=True, db_index=True, verbose_name="مرجع المزوّد")
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="سعر الصرف")

    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"

    def __str__(self):
        return f"Payment for Order {self.order.id} - Status: {self.status}"