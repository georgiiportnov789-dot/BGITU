from django.contrib import admin

from .models import Profile, Role, RoleRequest


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_developer', 'can_manage_roles', 'can_grade', 'is_system')
    search_fields = ('name', 'code')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'group', 'record_book')
    list_filter = ('role', 'group')
    search_fields = ('user__username', 'user__last_name')


@admin.register(RoleRequest)
class RoleRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'status', 'created_at', 'reviewed_by')
    list_filter = ('status', 'role')
