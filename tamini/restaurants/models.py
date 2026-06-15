from django.db import models
from accounts.models import User


class Restaurant(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='restaurants', null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    logo = models.ImageField(upload_to='restaurant_logos/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='restaurant_covers/', blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False, verbose_name="Approved")
    is_trendy = models.BooleanField(default=False, verbose_name="رائج")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


class HeroBanner(models.Model):
    title = models.CharField(max_length=255, verbose_name="العنوان")
    title_size = models.CharField(max_length=10, default='1.5rem', verbose_name="حجم العنوان", help_text="CSS font-size e.g. 1.5rem or 24px")
    title_color = models.CharField(max_length=7, default='#ffffff', verbose_name="لون العنوان", help_text="Hex colour code e.g. #ffffff")
    subtitle = models.TextField(blank=True, null=True, verbose_name="النص الفرعي")
    subtitle_size = models.CharField(max_length=10, default='1rem', verbose_name="حجم النص الفرعي", help_text="CSS font-size e.g. 1rem or 16px")
    subtitle_color = models.CharField(max_length=7, default='#ffffff', verbose_name="لون النص الفرعي", help_text="Hex colour code e.g. #ffffff")
    image = models.FileField(upload_to='banners/', null=True, verbose_name="الصورة أو الفيديو")
    cta_text = models.CharField(max_length=255, blank=True, null=True, verbose_name="نص الزر")
    cta_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="رابط الزر")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعلان رئيسي"
        verbose_name_plural = "الإعلانات الرئيسية"

    def __str__(self):
        return self.title

    @property
    def is_video(self):
        if not self.image:
            return False
        ext = self.image.name.lower().rsplit('.', 1)[-1]
        return ext in ('mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv')

    def get_categories(self):
        return Category.objects.filter(menu_items__restaurant=self).distinct()


class Category(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, null=True, blank=True, related_name='categories')
    def __str__(self):
        return self.name


class SiteContent(models.Model):
    welcome_title = models.CharField(max_length=255, verbose_name="عنوان الترحيب", default="أهلاً بك في طعميني")
    welcome_title_color = models.CharField(max_length=7, verbose_name="لون عنوان الترحيب", default="#f97316", help_text="Hex colour code e.g. #f97316")
    welcome_title_size = models.CharField(max_length=10, verbose_name="حجم عنوان الترحيب", default="1.875rem", help_text="CSS font-size e.g. 1.875rem or 24px")
    welcome_subtitle = models.TextField(verbose_name="النص الترحيبي", default="اكتشف الوجبات الأقرب إليك واستمتع بتجربة توصيل سريعة.")
    welcome_subtitle_color = models.CharField(max_length=7, verbose_name="لون النص الترحيبي", default="#6b7280", help_text="Hex colour code e.g. #6b7280")
    welcome_subtitle_size = models.CharField(max_length=10, verbose_name="حجم النص الترحيبي", default="1rem", help_text="CSS font-size e.g. 1rem or 16px")

    class Meta:
        verbose_name = "محتوى الموقع"
        verbose_name_plural = "محتوى الموقع"

    def __str__(self):
        return "إعدادات المحتوى"

    def save(self, *args, **kwargs):
        self.pk = 1
        kwargs.pop('force_insert', None)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='menu_items')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_items', null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


