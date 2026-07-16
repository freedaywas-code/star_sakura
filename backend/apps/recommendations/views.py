from django.db.models import Count

from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from common.response import ApiResponseMixin, ok

from .engine import (
    build_user_profile,
    log_action,
    recommend_artists,
    recommend_artworks_hybrid,
    recommend_artworks_popular,
)
from .models import UserAction, UserProfile
from .serializers import (
    ArtistRecommendationSerializer,
    ArtworkRecommendationSerializer,
    UserActionSerializer,
    UserProfileSerializer,
)


class RecommendationViewSet(ApiResponseMixin, GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="artworks")
    def recommend_artworks(self, request):
        limit = int(request.query_params.get("limit", 10))
        artworks = recommend_artworks_hybrid(request.user, limit=limit)

        result = []
        for artwork, score in artworks:
            artwork_data = ArtworkRecommendationSerializer(
                artwork, context={"request": request}
            ).data
            artwork_data["match_score"] = round(score, 3)
            result.append(artwork_data)

        return ok(result)

    @action(detail=False, methods=["get"], url_path="artists")
    def recommend_artists(self, request):
        limit = int(request.query_params.get("limit", 5))
        artists = recommend_artists(request.user, limit=limit)

        result = []
        for item in artists:
            artist_data = ArtistRecommendationSerializer(
                item["artist"], context={"request": request}
            ).data
            artist_data["match_score"] = round(item["match_score"], 3)
            artist_data["artwork_count"] = item["artwork_count"]
            artist_data["avg_rating"] = round(item["avg_rating"], 1) if item["avg_rating"] else 0
            artist_data["top_categories"] = item["top_categories"]
            result.append(artist_data)

        return ok(result)

    @action(detail=False, methods=["get"], url_path="popular")
    def popular_artworks(self, request):
        limit = int(request.query_params.get("limit", 10))
        artworks = recommend_artworks_popular(limit=limit, user=request.user)

        result = []
        for artwork, score in artworks:
            artwork_data = ArtworkRecommendationSerializer(
                artwork, context={"request": request}
            ).data
            artwork_data["match_score"] = round(score, 3)
            result.append(artwork_data)

        return ok(result)

    @action(detail=False, methods=["get"], url_path="profile")
    def user_profile(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        build_user_profile(request.user)
        profile.refresh_from_db()
        return ok(UserProfileSerializer(profile).data)

    @action(detail=False, methods=["post"], url_path="log-action")
    def log_user_action(self, request):
        action_type = request.data.get("action_type")
        artwork_id = request.data.get("artwork_id")
        tags = request.data.get("tags", [])

        if action_type not in dict(UserAction.ActionType.choices):
            return ok(None, message="无效的行为类型", code=400, status=status.HTTP_400_BAD_REQUEST)

        from apps.artworks.models import Artwork
        artwork = None
        if artwork_id:
            try:
                artwork = Artwork.objects.get(id=artwork_id)
            except Artwork.DoesNotExist:
                return ok(None, message="画作不存在", code=404, status=status.HTTP_404_NOT_FOUND)

        log_action(request.user, action_type, artwork, tags)
        return ok(None, message="行为记录成功")

    @action(detail=False, methods=["get"], url_path="preferences")
    def preferences(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        build_user_profile(request.user)
        profile.refresh_from_db()

        preferences = {
            "categories": profile.preferences.get("categories", {}),
            "tags": profile.preferences.get("tags", {}),
            "price_range": profile.price_range,
        }
        return ok(preferences)


class UserActionViewSet(ApiResponseMixin, GenericViewSet):
    serializer_class = UserActionSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="history")
    def action_history(self, request):
        limit = int(request.query_params.get("limit", 20))
        actions = UserAction.objects.filter(user=request.user).order_by("-created_at")[:limit]
        return ok(UserActionSerializer(actions, many=True).data)