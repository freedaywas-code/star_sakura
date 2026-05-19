from django.contrib.auth import get_user_model
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from urllib.parse import unquote

from common.response import ApiResponseMixin

from .models import Artwork
from .serializers import ArtworkSerializer


User = get_user_model()


class ArtworkViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    queryset = Artwork.objects.select_related("owner").all()
    serializer_class = ArtworkSerializer
    filterset_fields = ["owner", "category", "is_available"]
    search_fields = ["title", "description", "category"]
    ordering_fields = ["created_at", "updated_at", "price"]
    ordering = ["-created_at"]

    def _frontend_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        username = (
            self.request.headers.get("X-Star-Username")
            or self.request.data.get("owner_username")
            or self.request.query_params.get("owner_username")
            or "admin"
        )
        username = unquote(str(username))
        user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@local.star"})
        return user

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.AllowAny()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        serializer.save(owner=self._frontend_user())

    def _ensure_owner_or_admin(self, obj):
        user = self._frontend_user()
        if getattr(user, "is_admin", False) or obj.owner_id == user.id or user.username == "admin":
            return
        raise PermissionDenied("只能操作自己的画作")

    def perform_update(self, serializer):
        self._ensure_owner_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner_or_admin(instance)
        instance.delete()
