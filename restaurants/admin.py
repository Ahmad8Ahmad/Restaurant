from django.contrib import admin
from django.utils.html import format_html
from .models import Restaurant, MenuItem, Category

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_approved', 'phone']

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


