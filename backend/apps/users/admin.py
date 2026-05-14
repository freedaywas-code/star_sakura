from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["id", "username", "email", "is_admin", "is_staff", "is_active"]
    list_filter = ["is_admin", "is_staff", "is_active"]
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("星野樱平台信息", {"fields": ("is_admin", "avatar", "bio")}),
    )
