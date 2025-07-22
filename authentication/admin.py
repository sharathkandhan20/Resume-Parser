from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

class UserAdmin(BaseUserAdmin):
    ordering = ['email']
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_admin', 'is_active']
    search_fields = ['email', 'username']
    readonly_fields = ['id']
    list_filter = ['is_admin', 'is_active']  # ✅ ADD THIS LINE

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'mobile', 'role', 'date_of_joining', 'last_day_of_working')}),
        ('Permissions', {'fields': ('is_active', 'is_admin', 'is_superuser', 'groups', 'user_permissions')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name', 'mobile', 'password1', 'password2'),
        }),
    )


admin.site.register(User, UserAdmin)
