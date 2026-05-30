from django.contrib import admin

# Register your models here.
# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'phone', 'role', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('NagarikSetu Info', {'fields': ('phone', 'role')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)