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
    subtitle = models.TextField(blank=True, null=True, verbose_name="النص الفرعي")
    image = models.FileField(upload_to='banners/', null=True, verbose_name="الصورة أو الفيديو")
    cta_text = models.CharField(max_length=255, blank=True, null=True, verbose_name="نص الزر")
    cta_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="رابط الزر")
    text_color = models.CharField(max_length=7, default='#ffffff', verbose_name="لون النص")
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


