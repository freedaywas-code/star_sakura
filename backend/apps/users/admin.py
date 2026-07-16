from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

<<<<<<< HEAD
from .models import User
=======
from .models import DirectMessage, Follow, User
>>>>>>> origin/group_code


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["id", "username", "email", "is_admin", "is_staff", "is_active"]
    list_filter = ["is_admin", "is_staff", "is_active"]
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("星野樱平台信息", {"fields": ("is_admin", "avatar", "bio")}),
    )
<<<<<<< HEAD
=======


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ["id", "from_user", "to_user", "created_at"]
    search_fields = ["from_user__username", "to_user__username"]
    list_select_related = ["from_user", "to_user"]


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "sender", "recipient", "created_at", "read_at"]
    search_fields = ["sender__username", "recipient__username", "body"]
    list_filter = ["created_at", "read_at"]
    list_select_related = ["sender", "recipient"]
    readonly_fields = ["created_at", "read_at"]
>>>>>>> origin/group_code
