from rest_framework import serializers

from .models import CustomRequest


class CustomRequestSerializer(serializers.ModelSerializer):
    requester_username = serializers.CharField(source="requester.username", read_only=True)
    artist_username = serializers.CharField(source="artist.username", read_only=True)

    class Meta:
        model = CustomRequest
        fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "title",
            "description",
            "reference_image",
            "budget",
            "status",
            "progress",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "status",
            "progress",
            "created_at",
            "updated_at",
        ]
