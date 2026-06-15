from django.contrib import admin
from django.db.models import Sum, Q
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from decimal import Decimal
from modeltranslation.admin import TranslationAdmin
from .models import Restaurant, MenuItem, Category, HeroBanner, SiteContent
from orders.models import Order
from payments.models import Commission
from support.models import SiteSettings


def _current_rate():
    try:
        return SiteSettings.get_settings().get('commission_rate', 12)
    except Exception:
        return 12

@admin.register(Restaurant)
class RestaurantAdmin(TranslationAdmin):
    list_display = ['name', 'is_approved', 'is_trendy_badge', 'phone', 'total_revenue', 'total_commission', 'unsettled_commission', 'approval_badge']
    list_select_related = ['owner']
    list_filter = ['is_approved', 'is_trendy']
    actions = ['approve_restaurants', 'mark_trendy', 'unmark_trendy']

    fields = ['owner', 'name_ar', 'name_en', 'description_ar', 'description_en', 'address_ar', 'address_en',
              'latitude', 'longitude', 'phone', 'logo', 'cover_image', 'is_active', 'is_approved', 'is_trendy']

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

    @admin.display(description='Total Revenue')
    def total_revenue(self, obj):
        total = Order.objects.filter(
            restaurant=obj,
            status__in=['Delivered', 'Completed']
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        return f"{total:,.0f} ل.س"

    def total_commission(self, obj):
        total = Commission.objects.filter(
            commission_type='restaurant',
            order__restaurant=obj
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return f"{total:,.0f} ل.س"
    total_commission.short_description = 'Platform Commission'

    def get_list_display(self, request):
        rate = _current_rate()
        type(self).total_commission.short_description = f'Platform Commission ({rate}%)'
        return super().get_list_display(request)

    @admin.display(description='Unsettled')
    def unsettled_commission(self, obj):
        total = Commission.objects.filter(
            commission_type='restaurant',
            order__restaurant=obj,
            is_settled=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        color = 'red' if total > 0 else 'green'
        return format_html('<span style="color:{};font-weight:bold;">{} ل.س</span>',
                           color, f'{total:,.0f}')

@admin.register(MenuItem)
class MenuItemAdmin(TranslationAdmin):
    list_display = ['name', 'category', 'restaurant', 'price', 'is_available']
    list_filter = ['category', 'restaurant', 'is_available']

@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ['name', 'restaurant', 'image_preview']
    fields = ['name_ar', 'name_en', 'image', 'restaurant']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:8px;" />', obj.image.url)
        return '—'
    image_preview.short_description = 'الصورة'


@admin.register(HeroBanner)
class HeroBannerAdmin(TranslationAdmin):
    list_display = ['title', 'title_color_preview', 'image_preview', 'is_active', 'created_at']
    list_filter = ['is_active']
    ordering = ['-is_active', '-created_at']
    fields = ['title_ar', 'title_en', 'title_size', 'title_color', 'subtitle_ar', 'subtitle_en', 'subtitle_size', 'subtitle_color', 'image', 'cta_text_ar', 'cta_text_en', 'cta_url', 'is_active']

    def title_color_preview(self, obj):
        return format_html('<span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:{};border:1px solid #ddd;"></span>', obj.title_color)
    title_color_preview.short_description = 'اللون'

    def image_preview(self, obj):
        if not obj.image:
            return '—'
        if obj.is_video:
            return format_html('<video src="{}" width="80" height="45" style="object-fit:cover;border-radius:6px;" autoplay loop muted playsinline></video>', obj.image.url)
        return format_html('<img src="{}" width="80" height="45" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
    image_preview.short_description = 'الصورة'


@admin.register(SiteContent)
class SiteContentAdmin(TranslationAdmin):
    fields = ['welcome_title_ar', 'welcome_title_en', 'welcome_title_color', 'welcome_title_size', 'welcome_subtitle_ar', 'welcome_subtitle_en', 'welcome_subtitle_color', 'welcome_subtitle_size']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


