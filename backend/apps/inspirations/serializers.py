from rest_framework import serializers

from .models import Inspiration


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
