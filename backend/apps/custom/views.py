from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.caching import CachedPublicReadMixin
from common.response import ApiResponseMixin, ok
from common.throttling import WriteScopedThrottleMixin

from .models import CommissionOption, CustomRequest
from .serializers import CommissionOptionSerializer, CustomRequestSerializer


class CommissionOptionViewSet(CachedPublicReadMixin, ApiResponseMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionOptionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return CommissionOption.objects.filter(is_active=True).order_by("sort_order", "id")


class CustomRequestViewSet(CachedPublicReadMixin, WriteScopedThrottleMixin, ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = CustomRequestSerializer
    filterset_fields = ["status", "requester", "artist"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]
    ordering_fields = ["created_at", "updated_at", "budget", "progress"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = CustomRequest.objects.select_related("requester", "artist").all()
        public_statuses = [
            CustomRequest.Status.SUBMITTED,
            CustomRequest.Status.ACCEPTED,
            CustomRequest.Status.ABANDON_REQUESTED,
        ]
        if not self.request.user.is_authenticated:
            return queryset.filter(status__in=public_statuses)
        if self.request.user.is_admin:
            return queryset
        return queryset.filter(
            Q(status__in=public_statuses)
            | Q(requester=self.request.user)
            | Q(artist=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user, status=CustomRequest.Status.SUBMITTED)

    def _ensure_requester_or_admin(self, custom_request):
        if self.request.user.is_admin or custom_request.requester_id == self.request.user.id:
            return
        raise PermissionDenied("Only the requester or admin can modify this commission.")

    def _ensure_artist_or_admin(self, custom_request):
        if self.request.user.is_admin or custom_request.artist_id == self.request.user.id:
            return
        raise PermissionDenied("Only the artist or admin can update this commission.")

    def perform_update(self, serializer):
        custom_request = self.get_object()
        self._ensure_requester_or_admin(custom_request)
        if custom_request.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("Accepted commissions cannot be edited.")
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_requester_or_admin(instance)
        if instance.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("Accepted commissions cannot be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        with transaction.atomic():
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if custom_request.requester_id == request.user.id:
                raise ValidationError("You cannot accept your own commission.")
            if custom_request.status != CustomRequest.Status.SUBMITTED or custom_request.artist_id:
                raise ValidationError("This commission has already been accepted.")
            custom_request.artist = request.user
            custom_request.status = CustomRequest.Status.ACCEPTED
            custom_request.progress = max(custom_request.progress, 10)
            custom_request.accepted_at = timezone.now()
            custom_request.abandon_requested_at = None
            custom_request.save(update_fields=["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def abandon(self, request, pk=None):
        with transaction.atomic():
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            self._ensure_artist_or_admin(custom_request)
            if custom_request.status != CustomRequest.Status.ACCEPTED:
                raise ValidationError("This commission cannot be abandoned now.")

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
        with transaction.atomic():
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            self._ensure_requester_or_admin(custom_request)
            if custom_request.status != CustomRequest.Status.ABANDON_REQUESTED:
                raise ValidationError("There is no pending abandon request.")

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
        with transaction.atomic():
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            self._ensure_artist_or_admin(custom_request)
            try:
                progress = int(request.data.get("progress", custom_request.progress))
            except (TypeError, ValueError) as exc:
                raise ValidationError({"progress": "Progress must be a number."}) from exc
            status_value = request.data.get("status", custom_request.status)
            if status_value == "open":
                status_value = CustomRequest.Status.SUBMITTED
            if not 0 <= progress <= 100:
                raise ValidationError({"progress": "Progress must be between 0 and 100."})
            if status_value not in CustomRequest.Status.values:
                raise ValidationError({"status": "Invalid commission status."})
            custom_request.progress = progress
            custom_request.status = status_value
            custom_request.save(update_fields=["progress", "status", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
