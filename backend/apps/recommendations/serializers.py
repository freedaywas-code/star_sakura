from rest_framework import serializers

from apps.artworks.models import Artwork
from apps.users.models import User

from .models import UserAction, UserProfile


class UserActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAction
        fields = ["id", "user", "artwork", "action_type", "tags", "score", "created_at"]
        read_only_fields = ["id", "user", "score", "created_at"]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["id", "user", "preferences", "top_categories", "top_tags", "price_range", "updated_at"]
        read_only_fields = ["id", "user", "updated_at"]


class ArtworkRecommendationSerializer(serializers.ModelSerializer):
    owner_username = serializers.ReadOnlyField(source="owner.username")
    owner_avatar = serializers.ImageField(source="owner.avatar", read_only=True)
    reviews_total = serializers.IntegerField(read_only=True)
    match_score = serializers.FloatField(read_only=True)

    class Meta:
        model = Artwork
        fields = [
            "id", "title", "description", "image", "category", "tags",
            "price", "is_available", "created_at", "owner_username",
            "owner_avatar", "reviews_total", "match_score"
        ]


class ArtistRecommendationSerializer(serializers.ModelSerializer):
    artwork_count = serializers.IntegerField(read_only=True)
    avg_rating = serializers.FloatField(read_only=True)
    match_score = serializers.FloatField(read_only=True)
    top_categories = serializers.JSONField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "avatar", "bio", "artwork_count",
            "avg_rating", "match_score", "top_categories"
        ]