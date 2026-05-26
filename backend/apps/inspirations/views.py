from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.response import ApiResponseMixin, ok

from .models import Inspiration, InspirationComment
from .serializers import InspirationCommentSerializer, InspirationSerializer


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
        if self.action == "comments" and self.request.method == "GET":
            return [permissions.AllowAny()]
        if self.action == "comment_like":
            return [permissions.IsAuthenticated()]
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

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        inspiration = self.get_object()
        if request.method == "GET":
            queryset = (
                InspirationComment.objects
                .filter(inspiration=inspiration)
                .select_related("reviewer", "parent")
                .order_by("created_at")
            )
            serializer = InspirationCommentSerializer(queryset, many=True, context={"request": request})
            return ok(serializer.data, status=status.HTTP_200_OK)

        parent_id = request.data.get("parent")
        parent = None
        if parent_id:
            try:
                parent = InspirationComment.objects.select_related("parent").get(pk=parent_id, inspiration=inspiration)
            except InspirationComment.DoesNotExist:
                raise ValidationError("Parent comment does not exist.")
            if parent.parent_id:
                raise ValidationError("Replies can only be nested two levels deep.")

        serializer = InspirationCommentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(inspiration=inspiration, parent=parent, reviewer=request.user)
        return ok(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"comments/(?P<comment_pk>[^/.]+)/like")
    def comment_like(self, request, pk=None, comment_pk=None):
        inspiration = self.get_object()
        try:
            comment = InspirationComment.objects.get(pk=comment_pk, inspiration=inspiration)
        except InspirationComment.DoesNotExist:
            raise ValidationError("Comment does not exist.")

        liked_by = list(comment.liked_by or [])
        if request.user.username in liked_by:
            liked_by.remove(request.user.username)
        else:
            liked_by.append(request.user.username)
        comment.liked_by = liked_by
        comment.like_count = len(liked_by)
        comment.save(update_fields=["liked_by", "like_count"])
        serializer = InspirationCommentSerializer(comment, context={"request": request})
        return ok(serializer.data, status=status.HTTP_200_OK)
