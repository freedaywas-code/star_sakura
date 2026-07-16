from rest_framework import serializers

from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    artwork_title = serializers.CharField(source="artwork.title", read_only=True)
    buyer_username = serializers.CharField(source="buyer.username", read_only=True)
    seller_username = serializers.CharField(source="seller.username", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "artwork",
            "artwork_title",
            "buyer",
            "buyer_username",
            "seller",
            "seller_username",
            "quantity",
            "total_price",
            "status",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "buyer",
            "buyer_username",
            "seller",
            "seller_username",
            "total_price",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("数量必须大于 0")
        return value

    def validate_artwork(self, artwork):
        if not artwork.is_available:
            raise serializers.ValidationError("该画作暂不可购买")
        return artwork
