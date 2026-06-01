from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Restaurant, MenuItem, Category

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_approved', 'phone', 'approval_badge']
    actions = ['approve_restaurants']

    def approve_restaurants(self, request, queryset):
        for restaurant in queryset:
            restaurant.is_approved = True
            restaurant.save()
            if restaurant.owner:
                restaurant.owner.is_approved = True
                restaurant.owner.is_active = True
                restaurant.owner.save()
        self.message_user(request, f"{queryset.count()} مطعم تمت الموافقة عليه بنجاح")
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


