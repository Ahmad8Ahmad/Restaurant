from django.contrib import admin
from django.db.models import Sum
from django.utils import timezone
from .models import Payment, Commission


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ['commission_type', 'order_link', 'delivery_link', 'amount', 'is_settled', 'settled_at', 'created_at']
    list_filter = ['commission_type', 'is_settled', 'created_at']
    search_fields = ['order__id', 'delivery__order__id']
    actions = ['mark_settled', 'mark_unsettled']
    date_hierarchy = 'created_at'

    def order_link(self, obj):
        if obj.order_id:
            from django.utils.html import format_html
            return format_html('<a href="{}">Order #{}</a>', f'/admin/orders/order/{obj.order_id}/change/', obj.order_id)
        return '—'
    order_link.short_description = 'الطلب'

    def delivery_link(self, obj):
        if obj.delivery_id:
            from django.utils.html import format_html
            return format_html('<a href="{}">Delivery #{}</a>', f'/admin/delivery/delivery/{obj.delivery_id}/change/', obj.delivery_id)
        return '—'
    delivery_link.short_description = 'التوصيل'

    def mark_settled(self, request, queryset):
        updated = queryset.update(is_settled=True, settled_at=timezone.now())
        self.message_user(request, f"{updated} عمولة تمت تسويتها بنجاح")
    mark_settled.short_description = "تسوية العمولات المحددة"

    def mark_unsettled(self, request, queryset):
        updated = queryset.update(is_settled=False, settled_at=None)
        self.message_user(request, f"{updated} عمولة تم إلغاء تسويتها")
    mark_unsettled.short_description = "إلغاء تسوية العمولات المحددة"


admin.site.register(Payment)
