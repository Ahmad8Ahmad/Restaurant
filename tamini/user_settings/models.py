from django.db import models
from django.conf import settings


class UserPreference(models.Model):
    THEME_CHOICES = (
        ('light', 'فاتح'),
        ('dark', 'داكن'),
        ('system', 'تلقائي'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences',
        verbose_name="المستخدم",
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light', verbose_name="المظهر")
    notify_order_updates = models.BooleanField(default=True, verbose_name="إشعارات تحديث الطلبات")
    notify_promotions = models.BooleanField(default=True, verbose_name="الإشعارات الترويجية")
    notify_email = models.BooleanField(default=True, verbose_name="إشعارات البريد الإلكتروني")

    class Meta:
        verbose_name = 'تفضيل المستخدم'
        verbose_name_plural = 'تفضيلات المستخدم'

    def __str__(self):
        return f"Preferences for {self.user.email}"

    @classmethod
    def get_or_create_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj
