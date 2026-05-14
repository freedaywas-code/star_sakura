from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.response import ApiResponseMixin, ok

from .models import CustomRequest
from .serializers import CustomRequestSerializer


User = get_user_model()


class CustomRequestViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = CustomRequestSerializer
    permission_classes = [permissions.AllowAny]
    filterset_fields = ["status", "requester", "artist"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]
    ordering_fields = ["created_at", "updated_at", "budget", "progress"]
    ordering = ["-created_at"]

    def _frontend_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        username = (
            self.request.headers.get("X-Star-Username")
            or self.request.data.get("requester_username")
            or self.request.data.get("artist_username")
            or self.request.query_params.get("owner_username")
            or "admin"
        )
        user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@local.star"})
        return user

    def get_queryset(self):
        queryset = CustomRequest.objects.select_related("requester", "artist").all()
        if self.request.user.is_authenticated and self.request.user.is_admin:
            return queryset
        user = self._frontend_user()
        return queryset.filter(
            Q(status__in=[CustomRequest.Status.SUBMITTED, CustomRequest.Status.ACCEPTED, CustomRequest.Status.ABANDON_REQUESTED])
            | Q(requester=user)
            | Q(artist=user)
        )

    def perform_create(self, serializer):
        serializer.save(requester=self._frontend_user(), status=CustomRequest.Status.SUBMITTED)

    def _ensure_requester_or_admin(self, custom_request):
        user = self._frontend_user()
        if getattr(user, "is_admin", False) or custom_request.requester_id == user.id or user.username == "admin":
            return user
        raise PermissionDenied("只能操作自己发布的委托")

    def _ensure_artist_or_admin(self, custom_request):
        user = self._frontend_user()
        if getattr(user, "is_admin", False) or custom_request.artist_id == user.id:
            return user
        raise PermissionDenied("只有接单人或管理员可以更新委托")

    def perform_update(self, serializer):
        custom_request = self.get_object()
        self._ensure_requester_or_admin(custom_request)
        if custom_request.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("已被接受的委托不能编辑")
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_requester_or_admin(instance)
        if instance.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("已被接受的委托不能删除")
        instance.delete()

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        custom_request = self.get_object()
        user = self._frontend_user()
        if custom_request.requester_id == user.id:
            raise ValidationError("不能接受自己发布的委托")
        if custom_request.status != CustomRequest.Status.SUBMITTED or custom_request.artist_id:
            raise ValidationError("这个委托已经被接受了")
        custom_request.artist = user
        custom_request.status = CustomRequest.Status.ACCEPTED
        custom_request.progress = max(custom_request.progress, 10)
        custom_request.accepted_at = timezone.now()
        custom_request.abandon_requested_at = None
        custom_request.save(update_fields=["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def abandon(self, request, pk=None):
        custom_request = self.get_object()
        self._ensure_artist_or_admin(custom_request)
        if custom_request.status != CustomRequest.Status.ACCEPTED:
            raise ValidationError("当前委托不能申请放弃")

        accepted_at = custom_request.accepted_at or custom_request.updated_at
        if accepted_at and timezone.now() - accepted_at <= timedelta(hours=1):
            custom_request.artist = None
            custom_request.status = CustomRequest.Status.SUBMITTED
            custom_request.progress = 0
            custom_request.accepted_at = None
            custom_request.abandon_requested_at = None
            update_fields = ["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"]
        else:
            custom_request.status = CustomRequest.Status.ABANDON_REQUESTED
            custom_request.abandon_requested_at = timezone.now()
            update_fields = ["status", "abandon_requested_at", "updated_at"]

        custom_request.save(update_fields=update_fields)
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def resolve_abandon(self, request, pk=None):
        custom_request = self.get_object()
        self._ensure_requester_or_admin(custom_request)
        if custom_request.status != CustomRequest.Status.ABANDON_REQUESTED:
            raise ValidationError("当前没有待处理的放弃申请")

        approved = request.data.get("approved", True)
        approved = approved is True or str(approved).lower() in {"1", "true", "yes", "on"}
        if approved:
            custom_request.artist = None
            custom_request.status = CustomRequest.Status.SUBMITTED
            custom_request.progress = 0
            custom_request.accepted_at = None
            update_fields = ["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"]
        else:
            custom_request.status = CustomRequest.Status.ACCEPTED
            update_fields = ["status", "abandon_requested_at", "updated_at"]
        custom_request.abandon_requested_at = None
        custom_request.save(update_fields=update_fields)
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def set_progress(self, request, pk=None):
        custom_request = self.get_object()
        self._ensure_artist_or_admin(custom_request)
        try:
            progress = int(request.data.get("progress", custom_request.progress))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"progress": "进度必须是数字"}) from exc
        status_value = request.data.get("status", custom_request.status)
        if status_value == "open":
            status_value = CustomRequest.Status.SUBMITTED
        if not 0 <= progress <= 100:
            raise ValidationError({"progress": "进度必须在 0 到 100 之间"})
        if status_value not in CustomRequest.Status.values:
            raise ValidationError({"status": "无效委托状态"})
        custom_request.progress = progress
        custom_request.status = status_value
        custom_request.save(update_fields=["progress", "status", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
