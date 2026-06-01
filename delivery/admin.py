from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import DriverProfile, Delivery

@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_approved', 'created_at', 'approval_badge', 'monthly_trips', 'monthly_earnings']
    list_filter = ['is_approved']
    search_fields = ['user__username', 'user__email']
    actions = ['approve_drivers']
    list_select_related = ['user']

    def monthly_trips(self, obj):
        now = timezone.now()
        return Delivery.objects.filter(
            delivery_person=obj.user,
            status='delivered',
            updated_at__month=now.month,
            updated_at__year=now.year
        ).count()
    monthly_trips.short_description = 'Current Month Trips'

    def monthly_earnings(self, obj):
        now = timezone.now()
        deliveries = Delivery.objects.filter(
            delivery_person=obj.user,
            status='delivered',
            updated_at__month=now.month,
            updated_at__year=now.year
        )
        total = sum(d.delivery_fee for d in deliveries)
        return f"{total} S.P."
    monthly_earnings.short_description = 'Current Month Earnings (S.P.)'

    def approve_drivers(self, request, queryset):
        for profile in queryset:
            profile.is_approved = True
            profile.save()
            profile.user.is_approved = True
            profile.user.is_active = True
            profile.user.save()
        self.message_user(request, f"{queryset.count()} سائق تمت الموافقة عليهم بنجاح")
    approve_drivers.short_description = "الموافقة على السائقين المحددين"

    def approval_badge(self, obj):
        if obj.is_approved:
            return mark_safe('<span style="color:green;font-weight:bold;">✓ مقبول</span>')
        return mark_safe('<span style="color:red;font-weight:bold;">✗ قيد المراجعة</span>')
    approval_badge.short_description = 'الحالة'

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ['order', 'delivery_person', 'status', 'is_settled', 'updated_at']
    list_filter = ['status', 'is_settled']
