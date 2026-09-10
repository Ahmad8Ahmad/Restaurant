from django.db import models
from django.conf import settings


class UserPreference(models.Model):
    THEME_CHOICES = (
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')
    notify_order_updates = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=True)
    notify_email = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'User Preference'
        verbose_name_plural = 'User Preferences'

    def __str__(self):
        return f"Preferences for {self.user.email}"

    @classmethod
    def get_or_create_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj
