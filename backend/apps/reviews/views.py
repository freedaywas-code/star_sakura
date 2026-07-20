from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.caching import CachedPublicReadMixin
from common.response import ApiResponseMixin, ok
from common.throttling import WriteScopedThrottleMixin

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(CachedPublicReadMixin, WriteScopedThrottleMixin, ApiResponseMixin, viewsets.ModelViewSet):
    queryset = Review.objects.select_related(
        "order", "artwork", "reviewer", "target_user", "parent", "parent__reviewer"
    ).prefetch_related("liked_users").all()
    serializer_class = ReviewSerializer
    filterset_fields = ["artwork", "reviewer", "target_user", "rating"]
    search_fields = ["content", "artwork__title", "reviewer__username", "target_user__username"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "like"]:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        queryset = self.queryset
        if self.action in ["list", "retrieve", "like"] or (self.request.user.is_authenticated and self.request.user.is_admin):
            return queryset
        return queryset.filter(Q(reviewer=self.request.user) | Q(target_user=self.request.user))

    def perform_create(self, serializer):
        order = serializer.validated_data.get("order")
        artwork = serializer.validated_data["artwork"]
        parent = serializer.validated_data.get("parent")
        reviewer = self.request.user
        if order and order.buyer_id != reviewer.id:
            raise ValidationError("Only the buyer can review this order.")
        target_user = parent.reviewer if parent else (order.seller if order else artwork.owner)
        serializer.save(reviewer=reviewer, target_user=target_user)

    def _ensure_reviewer_or_admin(self, review):
        if self.request.user.is_admin or review.reviewer_id == self.request.user.id:
            return
        raise PermissionDenied("Only the reviewer or admin can modify this review.")

    def perform_update(self, serializer):
        self._ensure_reviewer_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_reviewer_or_admin(instance)
        instance.delete()

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        with transaction.atomic():
            review = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if review.liked_users.filter(pk=request.user.pk).exists():
                review.liked_users.remove(request.user)
            else:
                review.liked_users.add(request.user)
            review.like_count = review.liked_users.count()
            review.liked_by = list(review.liked_users.values_list("username", flat=True))
            review.save(update_fields=["liked_by", "like_count"])
        serializer = self.get_serializer(review)
        return ok(serializer.data, status=status.HTTP_200_OK)
