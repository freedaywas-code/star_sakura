import base64
import uuid

from django.core.files.base import ContentFile
from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    artwork_title = serializers.CharField(source="artwork.title", read_only=True)
    reviewer_username = serializers.CharField(source="reviewer.username", read_only=True)
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    image_data = serializers.CharField(write_only=True, required=False, allow_blank=True)
    image_url = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "order",
            "artwork",
            "artwork_title",
            "reviewer",
            "reviewer_username",
            "target_user",
            "target_username",
            "rating",
            "content",
            "image",
            "image_data",
            "image_url",
            "like_count",
            "liked_by",
            "liked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reviewer",
            "reviewer_username",
            "target_user",
            "target_username",
            "image_url",
            "like_count",
            "liked_by",
            "liked",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"artwork": {"required": False}}

    def get_image_url(self, obj):
        if not obj.image:
            return ""
        return obj.image.url

    def get_liked(self, obj):
        request = self.context.get("request")
        username = ""
        if request:
            username = request.headers.get("X-Star-Username") or request.query_params.get("owner_username") or ""
            if request.user.is_authenticated:
                username = request.user.username
        return username in (obj.liked_by or [])

    def _decode_image(self, image_data):
        if not image_data:
            return None
        if ";base64," in image_data:
            header, image_data = image_data.split(";base64,", 1)
            ext = header.split("/")[-1] or "png"
        else:
            ext = "png"
        return ContentFile(base64.b64decode(image_data), name=f"{uuid.uuid4().hex}.{ext}")

    def create(self, validated_data):
        image_data = validated_data.pop("image_data", "")
        image = self._decode_image(image_data)
        if image:
            validated_data["image"] = image
        return super().create(validated_data)

    def validate(self, attrs):
        order = attrs.get("order")
        artwork = attrs.get("artwork")
        if order and artwork and order.artwork_id != artwork.id:
            raise serializers.ValidationError("评价的订单和画作不匹配")
        if order and not artwork:
            attrs["artwork"] = order.artwork
        return attrs
