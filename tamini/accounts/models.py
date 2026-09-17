from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'عميل'),
        ('restaurant', 'مطعم'),
        ('staff', 'موظف'),
        ('delivery', 'سائق'),
        ('admin', 'مدير'),
    )
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer', db_index=True, verbose_name="الدور")
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True, verbose_name="رقم الهاتف")
    address = models.TextField(blank=True, null=True, verbose_name="العنوان")
    firebase_uid = models.CharField(max_length=128, blank=True, null=True, unique=True, verbose_name="معرّف Firebase")
    otp_code = models.CharField(max_length=128, blank=True, null=True, verbose_name="رمز التحقق")
    otp_created_at = models.DateTimeField(blank=True, null=True, verbose_name="وقت إنشاء رمز التحقق")
    is_verified = models.BooleanField(default=False, verbose_name="موثّق")
    is_approved = models.BooleanField(default=False, verbose_name="مقبول")
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
        verbose_name="المطعم",
    )

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_groups',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.email


class FCMDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fcm_devices')
    token = models.TextField(unique=True)
    platform = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.token[:16]}..."


class PendingSignup(models.Model):
    """Records the role a visitor selected during a public signup so the
    Django user is created with the right role even when the first verified
    login arrives without a role (manual login, phone, Google, or a
    verification link opened on another device).  Consumed once when the
    user record is created or upgraded, then deleted."""

    ROLE_CHOICES = (
        ('customer', 'عميل'),
        ('restaurant', 'مطعم'),
        ('delivery', 'سائق'),
    )
    email = models.EmailField(blank=True, null=True, unique=True, verbose_name="البريد الإلكتروني")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم الهاتف")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="الدور")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "طلب تسجيل قيد المراجعة"
        verbose_name_plural = "طلبات تسجيل قيد المراجعة"
        indexes = [
            models.Index(fields=['phone'])
        ]

    def __str__(self):
        return f"{self.email or self.phone} -> {self.role}"


