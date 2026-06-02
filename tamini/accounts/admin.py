from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import User


@admin.register(User)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'role', 'is_approved', 'is_active', 'approval_badge')
    list_filter = ('role', 'is_approved', 'is_active')
    search_fields = ('email', 'username')
    actions = ['approve_users']

    def approve_users(self, request, queryset):
        updated = queryset.update(is_approved=True, is_active=True)
        self.message_user(request, f"{updated} تمت الموافقة على الحسابات المحددة بنجاح")
    approve_users.short_description = "الموافقة على الحسابات المحددة (مطاعم/توصيل)"

    def approval_badge(self, obj):
        if obj.is_approved:
            return mark_safe('<span style="color:green;font-weight:bold;">✓ مقبول</span>')
        return mark_safe('<span style="color:red;font-weight:bold;">✗ قيد المراجعة</span>')
    approval_badge.short_description = 'الحالة'
