from rest_framework import serializers

from common.images import decode_base64_image

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    artwork_title = serializers.CharField(source="artwork.title", read_only=True)
    reviewer_username = serializers.CharField(source="reviewer.username", read_only=True)
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    parent_reviewer_username = serializers.CharField(source="parent.reviewer.username", read_only=True, default="")
    image_data = serializers.CharField(write_only=True, required=False, allow_blank=True)
    image_url = serializers.SerializerMethodField()
    liked_by = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "order",
            "artwork",
            "artwork_title",
            "parent",
            "parent_reviewer_username",
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
            "parent_reviewer_username",
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
        user_id = request.user.id if request and request.user.is_authenticated else None
        return bool(user_id and user_id in self._liked_user_ids(obj))

    def get_liked_by(self, obj):
        return self._liked_usernames(obj)

    def _liked_user_cache(self, obj):
        if not hasattr(obj, "_liked_user_cache"):
            users = list(obj.liked_users.all())
            obj._liked_user_cache = {
                "ids": {user.id for user in users},
                "usernames": [user.username for user in users],
            }
        return obj._liked_user_cache

    def _liked_user_ids(self, obj):
        return self._liked_user_cache(obj)["ids"]

    def _liked_usernames(self, obj):
        return self._liked_user_cache(obj)["usernames"]

    def _decode_image(self, image_data):
        return decode_base64_image(image_data)

    def create(self, validated_data):
        image_data = validated_data.pop("image_data", "")
        image = self._decode_image(image_data)
        if image:
            validated_data["image"] = image
        return super().create(validated_data)

    def validate(self, attrs):
        order = attrs.get("order")
        artwork = attrs.get("artwork")
        parent = attrs.get("parent")
        if order and artwork and order.artwork_id != artwork.id:
            raise serializers.ValidationError("评价的订单和画作不匹配")
        if order and not artwork:
            attrs["artwork"] = order.artwork
            artwork = order.artwork
        if parent and not artwork:
            attrs["artwork"] = parent.artwork
            artwork = parent.artwork
        if parent and artwork and parent.artwork_id != artwork.id:
            raise serializers.ValidationError("回复必须属于同一个作品")
        if parent and parent.parent_id:
            raise serializers.ValidationError("作品评价回复最多支持 2 层")
        return attrs
