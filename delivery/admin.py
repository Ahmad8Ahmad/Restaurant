from django.contrib import admin
from .models import DriverProfile, Delivery

@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_approved', 'created_at']
    list_filter = ['is_approved']
    search_fields = ['user__username', 'user__email']

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ['order', 'delivery_person', 'status', 'is_settled', 'updated_at']
    list_filter = ['status', 'is_settled']
