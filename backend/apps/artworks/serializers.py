import base64
import uuid

from django.core.files.base import ContentFile
from rest_framework import serializers

from .models import Artwork


class ArtworkSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    image_data = serializers.CharField(write_only=True, required=False, allow_blank=True)
    image_url = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta:
        model = Artwork
        fields = [
            "id",
            "owner",
            "owner_username",
            "title",
            "description",
            "image",
            "image_data",
            "image_url",
            "category",
            "tags",
            "price",
            "is_available",
            "reviews_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "owner_username", "image_url", "reviews_count", "created_at", "updated_at"]

    def get_image_url(self, obj):
        if not obj.image:
            return ""
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    def get_reviews_count(self, obj):
        return obj.reviews.count()

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

    def update(self, instance, validated_data):
        image_data = validated_data.pop("image_data", None)
        if image_data is not None:
            image = self._decode_image(image_data)
            if image:
                validated_data["image"] = image
        return super().update(instance, validated_data)

    def validate_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("标签必须是数组")
        return value
