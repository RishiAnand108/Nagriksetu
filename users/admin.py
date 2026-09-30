# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'email_verified', 'role', 'ward', 'complaint_count', 'is_staff']
    list_filter = ['role', 'ward', 'email_verified', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'phone', 'first_name', 'last_name']
    list_select_related = ['ward']
    autocomplete_fields = ['ward']

    fieldsets = UserAdmin.fieldsets + (
        ('NagrikSetu', {'fields': ('phone', 'role', 'ward', 'notify_by_email', 'email_verified')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('NagrikSetu', {'fields': ('email', 'phone', 'role', 'ward')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count('complaints'))

    @admin.display(description='Complaints', ordering='n')
    def complaint_count(self, obj):
        return obj.n
