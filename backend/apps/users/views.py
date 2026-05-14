from django.contrib.auth import get_user_model
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework_simplejwt.views import TokenObtainPairView

from common.response import ApiResponseMixin, ok

from .permissions import IsAdmin
from .serializers import AdminUserSerializer, LoginSerializer, RegisterSerializer, UserSerializer


User = get_user_model()


class RegisterView(ApiResponseMixin, CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(ApiResponseMixin, TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]


class MeView(ApiResponseMixin, RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


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
