from django.db.models import Count
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from common.response import ApiResponseMixin

from .models import Artwork
from .serializers import ArtworkSerializer


class ArtworkViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = ArtworkSerializer
    filterset_fields = ["owner", "category", "is_available"]
    search_fields = ["title", "description", "category"]
    ordering_fields = ["created_at", "updated_at", "price"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Artwork.objects.select_related("owner").annotate(reviews_total=Count("reviews")).all()

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _ensure_owner_or_admin(self, obj):
        if self.request.user.is_admin or obj.owner_id == self.request.user.id:
            return
        raise PermissionDenied("Only the owner or admin can modify this artwork.")

    def perform_update(self, serializer):
        self._ensure_owner_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner_or_admin(instance)
        instance.delete()
