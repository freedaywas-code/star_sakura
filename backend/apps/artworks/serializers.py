from rest_framework import serializers

from common.images import decode_base64_image

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
        return obj.image.url

    def get_reviews_count(self, obj):
        if hasattr(obj, "reviews_total"):
            return obj.reviews_total
        return obj.reviews.count()

    def _decode_image(self, image_data):
        return decode_base64_image(image_data)

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
