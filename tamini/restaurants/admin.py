from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Restaurant, MenuItem, Category, HeroBanner

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_approved', 'is_trendy_badge', 'phone', 'approval_badge']
    list_filter = ['is_approved', 'is_trendy']
    actions = ['approve_restaurants', 'mark_trendy', 'unmark_trendy']

    fields = ['owner', 'name', 'description', 'address', 'latitude', 'longitude',
              'phone', 'logo', 'cover_image', 'is_active', 'is_approved', 'is_trendy']

    def approve_restaurants(self, request, queryset):
        updated = 0
        for restaurant in queryset:
            if restaurant.is_approved:
                continue
            restaurant.is_approved = True
            restaurant.save(update_fields=['is_approved'])
            if restaurant.owner and not restaurant.owner.is_active:
                restaurant.owner.is_active = True
                restaurant.owner.is_approved = True
                restaurant.owner.save(update_fields=['is_active', 'is_approved'])
            updated += 1
        self.message_user(request, f"{updated} مطعم تمت الموافقة عليه بنجاح")
    approve_restaurants.short_description = "الموافقة على المطاعم المحددة"

    def mark_trendy(self, request, queryset):
        updated = queryset.update(is_trendy=True)
        self.message_user(request, f"{updated} مطعم تمت إضافته إلى الرائجة")
    mark_trendy.short_description = "تحديد كمطاعم رائجة"

    def unmark_trendy(self, request, queryset):
        updated = queryset.update(is_trendy=False)
        self.message_user(request, f"{updated} مطعم تمت إزالته من الرائجة")
    unmark_trendy.short_description = "إزالة من المطاعم الرائجة"

    def approval_badge(self, obj):
        if obj.is_approved:
            return mark_safe('<span style="color:green;font-weight:bold;">✓ مقبول</span>')
        return mark_safe('<span style="color:red;font-weight:bold;">✗ قيد المراجعة</span>')
    approval_badge.short_description = 'الحالة'

    @admin.display(description='رائج', boolean=True)
    def is_trendy_badge(self, obj):
        return obj.is_trendy

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'restaurant', 'price', 'is_available']
    list_filter = ['category', 'restaurant', 'is_available']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'image_preview']
    fields = ['name', 'image']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:8px;" />', obj.image.url)
        return '—'
    image_preview.short_description = 'الصورة'


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ['title', 'color_preview', 'image_preview', 'is_active', 'created_at']
    list_filter = ['is_active']
    ordering = ['-is_active', '-created_at']
    fields = ['title', 'subtitle', 'image', 'text_color', 'cta_text', 'cta_url', 'is_active']

    def color_preview(self, obj):
        return format_html('<span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:{};border:1px solid #ddd;"></span>', obj.text_color)
    color_preview.short_description = 'اللون'

    def image_preview(self, obj):
        if not obj.image:
            return '—'
        if obj.is_video:
            return format_html('<video src="{}" width="80" height="45" style="object-fit:cover;border-radius:6px;" autoplay loop muted playsinline></video>', obj.image.url)
        return format_html('<img src="{}" width="80" height="45" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
    image_preview.short_description = 'الصورة'


