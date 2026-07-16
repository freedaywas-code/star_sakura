from django.urls import path

from .chat_views import ChatViewSet
from .views import RecommendationViewSet, UserActionViewSet

urlpatterns = [
    path("", RecommendationViewSet.as_view({"get": "recommend_artworks"}), name="recommend-artworks"),
    path("artworks/", RecommendationViewSet.as_view({"get": "recommend_artworks"}), name="recommend-artworks"),
    path("artists/", RecommendationViewSet.as_view({"get": "recommend_artists"}), name="recommend-artists"),
    path("popular/", RecommendationViewSet.as_view({"get": "popular_artworks"}), name="popular-artworks"),
    path("profile/", RecommendationViewSet.as_view({"get": "user_profile"}), name="user-profile"),
    path("preferences/", RecommendationViewSet.as_view({"get": "preferences"}), name="preferences"),
    path("log-action/", RecommendationViewSet.as_view({"post": "log_user_action"}), name="log-action"),
    path("history/", UserActionViewSet.as_view({"get": "action_history"}), name="action-history"),
    path("chat/send/", ChatViewSet.as_view({"post": "send_message"}), name="chat-send"),
    path("chat/stream/", ChatViewSet.as_view({"post": "send_message_stream"}), name="chat-stream"),
    path("chat/history/", ChatViewSet.as_view({"get": "get_history"}), name="chat-history"),
    path("chat/new/", ChatViewSet.as_view({"post": "new_conversation"}), name="chat-new"),
    path("chat/clear/", ChatViewSet.as_view({"post": "clear_history"}), name="chat-clear"),
    path("chat/conversations/", ChatViewSet.as_view({"get": "list_conversations"}), name="chat-conversations"),
]