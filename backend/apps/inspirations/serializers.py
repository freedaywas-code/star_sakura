from rest_framework import serializers

from .models import Inspiration, InspirationComment


class InspirationSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Inspiration
        fields = [
            "id",
            "owner",
            "owner_username",
            "title",
            "tag",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "owner_username", "created_at", "updated_at"]


class InspirationCommentSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source="reviewer.username", read_only=True)
    liked = serializers.SerializerMethodField()

    class Meta:
        model = InspirationComment
        fields = [
            "id",
            "inspiration",
            "parent",
            "reviewer",
            "reviewer_username",
            "content",
            "like_count",
            "liked_by",
            "liked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "inspiration",
            "reviewer",
            "reviewer_username",
            "like_count",
            "liked_by",
            "liked",
            "created_at",
            "updated_at",
        ]

    def get_liked(self, obj):
        request = self.context.get("request")
        username = request.user.username if request and request.user.is_authenticated else ""
        return username in (obj.liked_by or [])
