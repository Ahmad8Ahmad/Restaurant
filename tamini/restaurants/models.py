from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from accounts.models import User
from tamini.media import OptimizedImageField, OptimizedMediaField


class Restaurant(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='restaurants', null=True, blank=True, verbose_name="المالك")
    name = models.CharField(max_length=255, verbose_name="اسم المطعم")
    description = models.TextField(blank=True, null=True, verbose_name="الوصف")
    address = models.TextField(blank=True, null=True, verbose_name="العنوان")
    latitude = models.FloatField(blank=True, null=True, verbose_name="خط العرض")
    longitude = models.FloatField(blank=True, null=True, verbose_name="خط الطول")
    logo = OptimizedImageField(upload_to='restaurant_logos/', blank=True, null=True, verbose_name="الشعار")
    cover_image = OptimizedImageField(upload_to='restaurant_covers/', blank=True, null=True, verbose_name="الصورة الغلاف")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم الهاتف")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="نشط")
    is_approved = models.BooleanField(default=False, verbose_name="مقبول", db_index=True)
    is_trendy = models.BooleanField(default=False, verbose_name="رائج", db_index=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="رسوم التوصيل")
    delivery_fee_per_km = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="رسوم التوصيل لكل كم")
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الحد الأدنى للطلب")
    delivery_radius_km = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="نصف قطر التوصيل (كم)")
    has_own_delivery = models.BooleanField(default=True, verbose_name="توصيل خاص")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "مطعم"
        verbose_name_plural = "المطاعم"
        indexes = [
            models.Index(fields=['is_approved', 'is_trendy']),
        ]

    def __str__(self):
        return self.name


class HeroBanner(models.Model):
    title = models.CharField(max_length=255, verbose_name="العنوان")
    title_size = models.CharField(max_length=10, default='1.5rem', verbose_name="حجم العنوان", help_text="CSS font-size e.g. 1.5rem or 24px")
    title_color = models.CharField(max_length=7, default='#ffffff', verbose_name="لون العنوان", help_text="Hex colour code e.g. #ffffff")
    subtitle = models.TextField(blank=True, null=True, verbose_name="النص الفرعي")
    subtitle_size = models.CharField(max_length=10, default='1rem', verbose_name="حجم النص الفرعي", help_text="CSS font-size e.g. 1rem or 16px")
    subtitle_color = models.CharField(max_length=7, default='#ffffff', verbose_name="لون النص الفرعي", help_text="Hex colour code e.g. #ffffff")
    image = OptimizedMediaField(upload_to='banners/', null=True, verbose_name="الصورة أو الفيديو")
    cta_text = models.CharField(max_length=255, blank=True, null=True, verbose_name="نص الزر")
    cta_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="رابط الزر")
    is_active = models.BooleanField(default=True, verbose_name="نشط", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعلان رئيسي"
        verbose_name_plural = "الإعلانات الرئيسية"
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.title

    @property
    def is_video(self):
        if not self.image:
            return False
        ext = self.image.name.lower().rsplit('.', 1)[-1]
        return ext in ('mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv')

    def get_categories(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'menu_items' in cache:
            seen = set()
            result = []
            for mi in cache['menu_items']:
                cat = mi.category
                if cat and cat.id not in seen:
                    seen.add(cat.id)
                    result.append(cat)
            return result
        return Category.objects.filter(menu_items__restaurant=self).distinct()


class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name="الاسم")
    image = OptimizedImageField(upload_to='categories/', blank=True, null=True, verbose_name="الصورة")
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, null=True, blank=True, related_name='categories', verbose_name="المطعم")

    class Meta:
        verbose_name = "فئة"
        verbose_name_plural = "الفئات"
        indexes = [
            models.Index(fields=['restaurant']),
        ]

    def __str__(self):
        return self.name


class SiteContent(models.Model):
    welcome_title = models.CharField(max_length=255, verbose_name="عنوان الترحيب", default="أهلاً بك في طعميني")
    welcome_title_color = models.CharField(max_length=7, verbose_name="لون عنوان الترحيب", default="#f97316", help_text="Hex colour code e.g. #f97316")
    welcome_title_size = models.CharField(max_length=10, verbose_name="حجم عنوان الترحيب", default="1.875rem", help_text="CSS font-size e.g. 1.875rem or 24px")
    welcome_subtitle = models.TextField(verbose_name="النص الترحيبي", default="اكتشف الوجبات الأقرب إليك واستمتع بتجربة توصيل سريعة.")
    welcome_subtitle_color = models.CharField(max_length=7, verbose_name="لون النص الترحيبي", default="#6b7280", help_text="Hex colour code e.g. #6b7280")
    welcome_subtitle_size = models.CharField(max_length=10, verbose_name="حجم النص الترحيبي", default="1rem", help_text="CSS font-size e.g. 1rem or 16px")
    terms_of_service = models.TextField(blank=True, verbose_name="شروط الخدمة", help_text="يُعرض في صفحة شروط الخدمة /legal/terms/ (يدعم HTML)")
    privacy_policy = models.TextField(blank=True, verbose_name="سياسة الخصوصية", help_text="يُعرض في صفحة سياسة الخصوصية /legal/privacy/ (يدعم HTML)")

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
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='menu_items', verbose_name="الفئة")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_items', null=True, blank=True, verbose_name="المطعم")
    name = models.CharField(max_length=255, verbose_name="الاسم")
    description = models.TextField(blank=True, null=True, verbose_name="الوصف")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر")
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, db_index=True, verbose_name="السعر بعد التخفيض")
    image = OptimizedImageField(upload_to='menu_items/', blank=True, null=True, verbose_name="الصورة")
    is_available = models.BooleanField(default=True, db_index=True, verbose_name="متاح")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "عنصر قائمة"
        verbose_name_plural = "عناصر القائمة"
        indexes = [
            models.Index(fields=['restaurant', 'is_available']),
            models.Index(fields=['restaurant', 'category']),
        ]

    def __str__(self):
        return self.name


@receiver([post_save, post_delete], sender=HeroBanner)
def clear_hero_banner_cache(sender, **kwargs):
    cache.delete('hero_banner')


@receiver([post_save, post_delete], sender=Category)
def clear_category_cache(sender, **kwargs):
    cache.delete('global_categories')


