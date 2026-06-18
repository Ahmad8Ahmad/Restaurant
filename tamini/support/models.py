from django.db import models
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    email = models.EmailField(default='taminyfood@gmail.com', verbose_name=_("البريد الإلكتروني"))
    phone = models.CharField(max_length=30, default='+963 900 000 000', verbose_name=_("رقم الهاتف"))
    whatsapp = models.CharField(max_length=30, default='963900000000', verbose_name=_("رقم واتساب"))
    instagram = models.URLField(default='https://instagram.com/taminy', verbose_name=_("إنستغرام"))
    facebook = models.URLField(default='https://facebook.com/taminy', verbose_name=_("فيسبوك"))
    commission_rate = models.PositiveSmallIntegerField(default=12, verbose_name=_("نسبة العمولة (%)"), help_text="مثلاً 12 يعني 12%")
    delivery_base_fee = models.PositiveIntegerField(default=200, verbose_name=_("أجرة التوصيل الأساسية (ل.س)"))
    delivery_per_km_fee = models.PositiveIntegerField(default=1500, verbose_name=_("أجرة التوصيل لكل كم (ل.س)"))
    x = models.URLField(default='https://x.com/taminy', verbose_name=_("X (تويتر)"))
    snapchat = models.URLField(default='https://snapchat.com/add/taminy', verbose_name=_("سناب شات"))
    tiktok = models.URLField(default='https://tiktok.com/@taminy', verbose_name=_("تيك توك"))
    stripe_publishable_key = models.CharField(max_length=255, blank=True, default='', verbose_name=_("مفتاح Stripe العام (pk_test)"))
    stripe_secret_key = models.CharField(max_length=255, blank=True, default='', verbose_name=_("مفتاح Stripe السري (sk_test)"))
    stripe_currency = models.CharField(max_length=3, default='usd', verbose_name=_("عملة Stripe"))
    stripe_exchange_rate = models.PositiveIntegerField(default=13000, verbose_name=_("سعر الصرف (ل.س لكل 1 من عملة Stripe)"), help_text=_("مثلاً 13000 يعني 1 دولار = 13000 ل.س"))

    class Meta:
        verbose_name = _("إعدادات الموقع")
        verbose_name_plural = _("إعدادات الموقع")

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
                'commission_rate': obj.commission_rate,
                'delivery_base_fee': obj.delivery_base_fee,
                'delivery_per_km_fee': obj.delivery_per_km_fee,
                'stripe_publishable_key': obj.stripe_publishable_key,
                'stripe_secret_key': obj.stripe_secret_key,
                'stripe_currency': obj.stripe_currency,
                'stripe_exchange_rate': obj.stripe_exchange_rate,
            }
            cache.set('site_settings', data, 3600)
        return data

    def __str__(self):
        return str(_("إعدادات الموقع"))


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('open', _('مفتوح')),
        ('in_progress', _('قيد المعالجة')),
        ('resolved', _('تم الحل')),
        ('closed', _('مغلق')),
    ]
    PRIORITY_CHOICES = [
        ('low', _('منخفض')),
        ('medium', _('متوسط')),
        ('high', _('عالي')),
        ('urgent', _('عاجل')),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='support_tickets'
    )
    customer_name = models.CharField(max_length=255, blank=True, verbose_name=_("اسم المرسل"))
    customer_email = models.EmailField(verbose_name=_("البريد الإلكتروني"))
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name=_("رقم الهاتف"))
    order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='support_tickets'
    )
    subject = models.CharField(max_length=255, verbose_name=_("الموضوع"))
    description = models.TextField(verbose_name=_("الوصف"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("تذكرة دعم")
        verbose_name_plural = _("تذاكر الدعم")

    def __str__(self):
        return f"#{self.id} {self.subject}"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    author_name = models.CharField(max_length=255, blank=True)
    message = models.TextField(verbose_name=_("الرسالة"))
    attachment = models.FileField(upload_to='support/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _("رسالة دعم")
        verbose_name_plural = _("رسائل الدعم")

    def __str__(self):
        return _("رسالة في %(ticket)s") % {'ticket': self.ticket}
