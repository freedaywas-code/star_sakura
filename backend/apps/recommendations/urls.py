from django.urls import path

from .views import AIChatViewSet
from .settings_views import AISettingsTestViewSet, AISettingsViewSet


urlpatterns = [
    path(
        "settings/",
        AISettingsViewSet.as_view(
            {"get": "retrieve_settings", "put": "update_settings", "delete": "delete_settings"}
        ),
        name="ai-settings",
    ),
    path(
        "settings/test/",
        AISettingsTestViewSet.as_view({"post": "test_connection"}),
        name="ai-settings-test",
    ),
    path("chat/send/", AIChatViewSet.as_view({"post": "send_message"}), name="ai-chat-send"),
    path("chat/stream/", AIChatViewSet.as_view({"post": "send_message_stream"}), name="ai-chat-stream"),
    path("chat/history/", AIChatViewSet.as_view({"get": "get_history"}), name="ai-chat-history"),
    path("chat/new/", AIChatViewSet.as_view({"post": "new_conversation"}), name="ai-chat-new"),
    path("chat/clear/", AIChatViewSet.as_view({"post": "clear_history"}), name="ai-chat-clear"),
    path("chat/conversations/", AIChatViewSet.as_view({"get": "list_conversations"}), name="ai-chat-conversations"),
]
