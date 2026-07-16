from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "需要管理员权限"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsOwner(BasePermission):
    message = "只能操作自己的资源"

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None) or obj
        return bool(request.user and request.user.is_authenticated and owner == request.user)
