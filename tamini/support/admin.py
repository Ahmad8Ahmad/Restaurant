from django.contrib import admin
from .models import Ticket, TicketMessage, SiteSettings, SUPPORT_AGENT_GROUP


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'customer_name', 'assignee', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'assignee']
    search_fields = ['subject', 'customer_name', 'customer_email']
    autocomplete_fields = ['assignee']
    inlines = [TicketMessageInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'assignee':
            from django.contrib.auth.models import Group
            from django.db.models import Q
            try:
                group = Group.objects.get(name=SUPPORT_AGENT_GROUP)
                kwargs['queryset'] = db_field.remote_field.model.objects.filter(
                    Q(is_staff=True) | Q(groups=group) | Q(is_superuser=True)
                )
            except Group.DoesNotExist:
                kwargs['queryset'] = db_field.remote_field.model.objects.filter(is_staff=True)
            if request.user.is_superuser:
                kwargs['queryset'] = db_field.remote_field.model.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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
            'fields': ('stripe_mode', 'stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret', 'stripe_currency', 'stripe_exchange_rate'),
            'description': 'اضبط الحالة على "معطل" لإخفاء الدفع الإلكتروني داخل سوريا. اترك المفاتيح فارغة لتعطيل الدفع بالبطاقة. مفتاح Webhook تجده في Stripe Dashboard → Webhooks.',
        }),
    )

    def has_add_permission(self, request):
        return False if SiteSettings.objects.exists() else True

    def has_delete_permission(self, request, obj=None):
        return False
