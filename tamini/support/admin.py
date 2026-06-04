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
    list_display = ['email', 'phone']

    def has_add_permission(self, request):
        return False if SiteSettings.objects.exists() else True

    def has_delete_permission(self, request, obj=None):
        return False
