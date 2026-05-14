from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.response import ok
from common.response import ApiResponseMixin

from .models import Review
from .serializers import ReviewSerializer


User = get_user_model()


class ReviewViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    queryset = Review.objects.select_related("order", "artwork", "reviewer", "target_user").all()
    serializer_class = ReviewSerializer
    filterset_fields = ["artwork", "reviewer", "target_user", "rating"]
    search_fields = ["content", "artwork__title", "reviewer__username", "target_user__username"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]

    def _frontend_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        username = (
            self.request.headers.get("X-Star-Username")
            or self.request.data.get("reviewer_username")
            or self.request.query_params.get("owner_username")
            or "admin"
        )
        user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@local.star"})
        return user

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.AllowAny()]
        if self.action == "like":
            return [permissions.AllowAny()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        queryset = self.queryset
        if self.action in ["list", "retrieve"] or (self.request.user.is_authenticated and self.request.user.is_admin):
            return queryset
        user = self._frontend_user()
        return queryset.filter(Q(reviewer=user) | Q(target_user=user))

    def perform_create(self, serializer):
        order = serializer.validated_data.get("order")
        artwork = serializer.validated_data["artwork"]
        reviewer = self._frontend_user()
        if order and order.buyer_id != reviewer.id:
            raise ValidationError("只有买家可以评价该订单")
        target_user = order.seller if order else artwork.owner
        serializer.save(reviewer=reviewer, target_user=target_user)

    def _ensure_reviewer_or_admin(self, review):
        user = self._frontend_user()
        if getattr(user, "is_admin", False) or review.reviewer_id == user.id or user.username == "admin":
            return
        raise PermissionDenied("只能修改自己的评价")

    def perform_update(self, serializer):
        self._ensure_reviewer_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_reviewer_or_admin(instance)
        instance.delete()

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        review = self.get_object()
        user = self._frontend_user()
        liked_by = list(review.liked_by or [])
        if user.username in liked_by:
            liked_by.remove(user.username)
        else:
            liked_by.append(user.username)
        review.liked_by = liked_by
        review.like_count = len(liked_by)
        review.save(update_fields=["liked_by", "like_count"])
        serializer = self.get_serializer(review)
        return ok(serializer.data, status=status.HTTP_200_OK)
