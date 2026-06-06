from django.db import models
from django.conf import settings
from django.core.cache import cache


class SiteSettings(models.Model):
    email = models.EmailField(default='taminyfood@gmail.com', verbose_name="البريد الإلكتروني")
    phone = models.CharField(max_length=30, default='+963 900 000 000', verbose_name="رقم الهاتف")
    whatsapp = models.CharField(max_length=30, default='963900000000', verbose_name="رقم واتساب")
    instagram = models.URLField(default='https://instagram.com/taminy', verbose_name="إنستغرام")
    facebook = models.URLField(default='https://facebook.com/taminy', verbose_name="فيسبوك")
    delivery_base_fee = models.PositiveIntegerField(default=200, verbose_name="أجرة التوصيل الأساسية (ل.س)")
    delivery_per_km_fee = models.PositiveIntegerField(default=1500, verbose_name="أجرة التوصيل لكل كم (ل.س)")
    x = models.URLField(default='https://x.com/taminy', verbose_name="X (تويتر)")
    snapchat = models.URLField(default='https://snapchat.com/add/taminy', verbose_name="سناب شات")
    tiktok = models.URLField(default='https://tiktok.com/@taminy', verbose_name="تيك توك")

    class Meta:
        verbose_name = "إعدادات الموقع"
        verbose_name_plural = "إعدادات الموقع"

    def save(self, *args, **kwargs):
        cache.delete('site_settings')
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        data = cache.get('site_settings')
        if data is None:
            obj = cls.objects.first()
            if not obj:
                obj = cls.objects.create()
            data = {
                'email': obj.email,
                'phone': obj.phone,
                'whatsapp': obj.whatsapp,
                'instagram': obj.instagram,
                'facebook': obj.facebook,
                'x': obj.x,
                'snapchat': obj.snapchat,
                'tiktok': obj.tiktok,
                'delivery_base_fee': obj.delivery_base_fee,
                'delivery_per_km_fee': obj.delivery_per_km_fee,
            }
            cache.set('site_settings', data, 3600)
        return data

    def __str__(self):
        return "إعدادات الموقع"


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('open', 'مفتوح'),
        ('in_progress', 'قيد المعالجة'),
        ('resolved', 'تم الحل'),
        ('closed', 'مغلق'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'منخفض'),
        ('medium', 'متوسط'),
        ('high', 'عالي'),
        ('urgent', 'عاجل'),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='support_tickets'
    )
    customer_name = models.CharField(max_length=255, blank=True, verbose_name="اسم المرسل")
    customer_email = models.EmailField(verbose_name="البريد الإلكتروني")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="رقم الهاتف")
    order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='support_tickets'
    )
    subject = models.CharField(max_length=255, verbose_name="الموضوع")
    description = models.TextField(verbose_name="الوصف")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "تذكرة دعم"
        verbose_name_plural = "تذاكر الدعم"

    def __str__(self):
        return f"#{self.id} {self.subject}"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    author_name = models.CharField(max_length=255, blank=True)
    message = models.TextField(verbose_name="الرسالة")
    attachment = models.FileField(upload_to='support/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "رسالة دعم"
        verbose_name_plural = "رسائل الدعم"

    def __str__(self):
        return f"رسالة في {self.ticket}"
