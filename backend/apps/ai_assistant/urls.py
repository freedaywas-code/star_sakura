from django.urls import path

from .views import AIChatView, AIStatusView


urlpatterns = [
    path("status/", AIStatusView.as_view(), name="ai-status"),
    path("chat/", AIChatView.as_view(), name="ai-chat"),
]
