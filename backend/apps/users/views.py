from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from common.response import ApiResponseMixin, ok

from .permissions import IsAdmin
from .serializers import AdminUserSerializer, ChangePasswordSerializer, RegisterSerializer, UserSerializer


User = get_user_model()


class RegisterView(ApiResponseMixin, CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(ApiResponseMixin, APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    def post(self, request):
        raw_username = request.data.get("username") or request.data.get("email") or ""
        password = request.data.get("password") or ""
        username = str(raw_username).strip()
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
        auth_user = authenticate(request, username=user.get_username(), password=password) if user else None

        if not auth_user or not auth_user.is_active:
            if settings.DEBUG:
                print(
                    "[login debug]",
                    {
                        "content_type": getattr(request, "content_type", ""),
                        "keys": sorted(request.data.keys()),
                        "username_repr": repr(raw_username),
                        "normalized_username": username,
                        "password_length": len(password),
                        "user_found": bool(user),
                        "user_is_active": getattr(user, "is_active", None),
                        "password_matches": user.check_password(password) if user else False,
                    },
                )
            raise AuthenticationFailed("用户名或密码不正确。")

        refresh = RefreshToken.for_user(auth_user)
        refresh["username"] = auth_user.username
        refresh["is_admin"] = auth_user.is_admin
        access = refresh.access_token
        access["username"] = auth_user.username
        access["is_admin"] = auth_user.is_admin
        return ok({"refresh": str(refresh), "access": str(access)})


class MeView(ApiResponseMixin, RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(None, message="password updated", status=status.HTTP_200_OK)


class UserViewSet(ApiResponseMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "date_joined", "username"]

    def get_serializer_class(self):
        if self.request.user.is_authenticated and self.request.user.is_admin:
            return AdminUserSerializer
        return UserSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return self.queryset
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def set_admin(self, request, pk=None):
        user = self.get_object()
        user.is_admin = bool(request.data.get("is_admin", True))
        user.save(update_fields=["is_admin", "is_staff"])
        return ok(UserSerializer(user, context={"request": request}).data, status=status.HTTP_200_OK)
