from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.response import ApiResponseMixin, ok

from .models import CustomRequest
from .serializers import CustomRequestSerializer


class CustomRequestViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = CustomRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status", "requester", "artist"]
    search_fields = ["title", "description", "requester__username", "artist__username"]
    ordering_fields = ["created_at", "updated_at", "budget", "progress"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = CustomRequest.objects.select_related("requester", "artist").all()
        if self.request.user.is_admin:
            return queryset
        return queryset.filter(Q(requester=self.request.user) | Q(artist=self.request.user) | Q(status=CustomRequest.Status.SUBMITTED))

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    def _ensure_artist_or_admin(self, custom_request):
        if self.request.user.is_admin or custom_request.artist_id == self.request.user.id:
            return
        raise PermissionDenied("只有接单画师或管理员可以更新定制进度")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        custom_request = self.get_object()
        if custom_request.requester_id == request.user.id:
            raise ValidationError("不能接自己的定制需求")
        if custom_request.artist_id and not request.user.is_admin:
            raise ValidationError("该定制需求已被接单")
        custom_request.artist = request.user
        custom_request.status = CustomRequest.Status.ACCEPTED
        custom_request.progress = max(custom_request.progress, 10)
        custom_request.save(update_fields=["artist", "status", "progress", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def set_progress(self, request, pk=None):
        custom_request = self.get_object()
        self._ensure_artist_or_admin(custom_request)
        try:
            progress = int(request.data.get("progress", custom_request.progress))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"progress": "进度必须是数字"}) from exc
        status_value = request.data.get("status", custom_request.status)
        if not 0 <= progress <= 100:
            raise ValidationError({"progress": "进度必须在 0 到 100 之间"})
        if status_value not in CustomRequest.Status.values:
            raise ValidationError({"status": "无效定制状态"})
        custom_request.progress = progress
        custom_request.status = status_value
        custom_request.save(update_fields=["progress", "status", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
