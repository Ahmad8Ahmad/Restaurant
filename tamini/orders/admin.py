from django.contrib import admin
from .models import Order, OrderItem
from payments.models import Payment

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['menu_item', 'quantity', 'price']
    can_delete = False

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ['amount', 'payment_method', 'status', 'created_at']
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'restaurant', 'status', 'total_price', 'created_at']
    list_filter = ['status', 'created_at', 'restaurant']
    search_fields = ['id', 'customer__username', 'customer__email', 'restaurant__name']
    inlines = [OrderItemInline, PaymentInline]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'menu_item', 'quantity', 'price']
    list_filter = ['order__status']
    search_fields = ['order__id', 'menu_item__name']
