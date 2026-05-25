from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from common.response import ApiResponseMixin

from .models import Inspiration
from .serializers import InspirationSerializer


class InspirationViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = InspirationSerializer
    filterset_fields = ["owner", "tag"]
    search_fields = ["title", "tag", "content", "owner__username"]
    ordering_fields = ["created_at", "updated_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Inspiration.objects.select_related("owner").all()

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _ensure_owner_or_admin(self, obj):
        if self.request.user.is_admin or obj.owner_id == self.request.user.id:
            return
        raise PermissionDenied("Only the owner or admin can modify this inspiration.")

    def perform_update(self, serializer):
        self._ensure_owner_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner_or_admin(instance)
        instance.delete()
