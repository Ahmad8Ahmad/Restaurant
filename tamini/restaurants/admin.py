from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Restaurant, MenuItem, Category, HeroBanner

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_approved', 'phone', 'approval_badge']
    actions = ['approve_restaurants']

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

    def approval_badge(self, obj):
        if obj.is_approved:
            return mark_safe('<span style="color:green;font-weight:bold;">✓ مقبول</span>')
        return mark_safe('<span style="color:red;font-weight:bold;">✗ قيد المراجعة</span>')
    approval_badge.short_description = 'الحالة'

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
    list_display = ['title', 'is_active', 'created_at']
    list_filter = ['is_active']
    ordering = ['-is_active', '-created_at']


