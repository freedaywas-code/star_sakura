from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.response import ApiResponseMixin, ok

from .models import Order
from .serializers import OrderSerializer


class OrderViewSet(ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status", "buyer", "seller", "artwork"]
    search_fields = ["artwork__title", "buyer__username", "seller__username", "note"]
    ordering_fields = ["created_at", "updated_at", "total_price"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Order.objects.select_related("artwork", "buyer", "seller").all()
        if self.request.user.is_admin:
            return queryset
        return queryset.filter(Q(buyer=self.request.user) | Q(seller=self.request.user))

    def perform_create(self, serializer):
        artwork = serializer.validated_data["artwork"]
        quantity = serializer.validated_data.get("quantity", 1)
        if artwork.owner_id == self.request.user.id:
            raise ValidationError("不能购买自己的画作")
        serializer.save(
            buyer=self.request.user,
            seller=artwork.owner,
            total_price=artwork.price * quantity,
        )

    def _ensure_seller_or_admin(self, order):
        if self.request.user.is_admin or order.seller_id == self.request.user.id:
            return
        raise PermissionDenied("只有卖家或管理员可以执行该操作")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        order = self.get_object()
        self._ensure_seller_or_admin(order)
        order.status = Order.Status.ACCEPTED
        order.save(update_fields=["status", "updated_at"])
        return ok(OrderSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        order = self.get_object()
        self._ensure_seller_or_admin(order)
        status_value = request.data.get("status")
        if status_value not in Order.Status.values:
            raise ValidationError({"status": "无效订单状态"})
        order.status = status_value
        order.save(update_fields=["status", "updated_at"])
        return ok(OrderSerializer(order, context={"request": request}).data)
