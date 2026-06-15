from django.contrib import admin
from django.db.models import Sum
from django.utils.safestring import mark_safe
from django.utils import timezone
from decimal import Decimal
from .models import DriverProfile, Delivery
from payments.models import Commission
from support.models import SiteSettings


def _current_rate():
    try:
        return SiteSettings.get_settings().get('commission_rate', 12)
    except Exception:
        return 12

@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_approved', 'created_at', 'approval_badge', 'monthly_trips', 'monthly_earnings', 'total_commission', 'unsettled_commission']
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

    def total_commission(self, obj):
        total = Commission.objects.filter(
            commission_type='delivery',
            delivery__delivery_person=obj.user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return f"{total:,.0f} S.P."
    total_commission.short_description = 'Total Commission'

    def get_list_display(self, request):
        rate = _current_rate()
        type(self).total_commission.short_description = f'Total Commission ({rate}%)'
        type(self).unsettled_commission.short_description = 'Unsettled Commission'
        return super().get_list_display(request)

    @admin.display(description='Unsettled Commission')
    def unsettled_commission(self, obj):
        total = Commission.objects.filter(
            commission_type='delivery',
            delivery__delivery_person=obj.user,
            is_settled=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return mark_safe('<span style="color:{};font-weight:bold;">{:,.0f} S.P.</span>'.format(
            'red' if total > 0 else 'green', total))

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ['order', 'delivery_person', 'status', 'commission_amount', 'is_settled', 'updated_at']
    list_filter = ['status', 'is_settled']
    list_select_related = ['order', 'delivery_person']

    def commission_amount(self, obj):
        comm = Commission.objects.filter(
            commission_type='delivery',
            delivery=obj
        ).first()
        if comm:
            color = 'green' if comm.is_settled else 'red'
            return mark_safe(f'<span style="color:{color};font-weight:bold;">{comm.amount:,.0f} S.P.</span>')
        status = obj.status
        if status == 'delivered':
            return mark_safe('<span style="color:orange;">Pending</span>')
        return '—'
    commission_amount.short_description = 'Commission'

    def get_list_display(self, request):
        rate = _current_rate()
        type(self).commission_amount.short_description = f'Commission ({rate}%)'
        return super().get_list_display(request)
