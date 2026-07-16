from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

<<<<<<< HEAD
from .views import ChangePasswordView, LoginView, MeView, RegisterView, UserViewSet
=======
from .views import (
    ChangePasswordView,
    ConversationListView,
    FollowersView,
    FollowingView,
    FollowView,
    LoginView,
    MarkMessagesReadView,
    MeView,
    MessageHistoryView,
    PublicProfileView,
    RegisterView,
    UserViewSet,
)
>>>>>>> origin/group_code


router = DefaultRouter()
router.register("accounts", UserViewSet, basename="users")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("password/", ChangePasswordView.as_view(), name="password-change"),
<<<<<<< HEAD
=======
    path("profiles/<str:identifier>/", PublicProfileView.as_view(), name="public-profile"),
    path("profiles/<str:identifier>/follow/", FollowView.as_view(), name="profile-follow"),
    path("followers/", FollowersView.as_view(), name="followers"),
    path("following/", FollowingView.as_view(), name="following"),
    path("messages/conversations/", ConversationListView.as_view(), name="message-conversations"),
    path("messages/<str:identifier>/read/", MarkMessagesReadView.as_view(), name="message-read"),
    path("messages/<str:identifier>/", MessageHistoryView.as_view(), name="message-history"),
>>>>>>> origin/group_code
    path("", include(router.urls)),
]
