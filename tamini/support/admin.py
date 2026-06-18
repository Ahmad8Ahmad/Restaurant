from django.contrib import admin
from .models import Ticket, TicketMessage, SiteSettings


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'customer_name', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority']
    search_fields = ['subject', 'customer_name', 'customer_email']
    inlines = [TicketMessageInline]


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author_name', 'created_at']
    readonly_fields = ['created_at']


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['email', 'phone', 'commission_rate', 'delivery_base_fee', 'delivery_per_km_fee']
    fieldsets = (
        ('جهات الاتصال', {
            'fields': ('email', 'phone', 'whatsapp')
        }),
        ('التواصل الاجتماعي', {
            'fields': ('instagram', 'facebook', 'x', 'snapchat', 'tiktok')
        }),
        ('العمولات', {
            'fields': ('commission_rate',),
            'description': 'نسبة العمولة التي تحصل عليها المنصة (%)',
        }),
        ('أجور التوصيل', {
            'fields': ('delivery_base_fee', 'delivery_per_km_fee'),
            'description': 'تتحكم هذه القيم بحساب أجرة التوصيل للسائقين',
        }),
        ('Stripe (الدفع الإلكتروني)', {
            'fields': ('stripe_publishable_key', 'stripe_secret_key', 'stripe_currency', 'stripe_exchange_rate'),
            'description': 'مفاتيح وضع التجربة (sandbox) من Stripe. اتركها فارغة لتعطيل الدفع بالبطاقة.',
        }),
    )

    def has_add_permission(self, request):
        return False if SiteSettings.objects.exists() else True

    def has_delete_permission(self, request, obj=None):
        return False
