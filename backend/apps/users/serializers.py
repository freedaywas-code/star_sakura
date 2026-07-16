from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "avatar", "bio", "profile", "is_admin"]
        read_only_fields = ["id", "is_admin"]


class AdminUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        read_only_fields = ["id"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        validate_password(password)
        user = User(**validated_data)
        user.set_password(password)
        user.profile = {
            "displayName": user.username,
            "avatar": "",
            "intro": "",
            "philosophy": "",
            "skills": [],
            "gender": "",
            "birthday": "",
            "signature": "",
        }
        user.save()
        return user

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email is already registered.")
        return email


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        raw_username = attrs.get(self.username_field) or ""
        password = attrs.get("password") or ""
        username = raw_username.strip()
        user = None
        if username:
            user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
            if user:
                attrs[self.username_field] = user.get_username()
        try:
            return super().validate(attrs)
        except AuthenticationFailed:
            if settings.DEBUG:
                request = self.context.get("request")
                print(
                    "[login debug]",
                    {
                        "content_type": getattr(request, "content_type", ""),
                        "keys": sorted(self.initial_data.keys()),
                        "username_repr": repr(raw_username),
                        "normalized_username": username,
                        "password_length": len(password),
                        "user_found": bool(user),
                        "user_is_active": getattr(user, "is_active", None),
                        "password_matches": user.check_password(password) if user else False,
                    },
                )
            raise

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["is_admin"] = user.is_admin
        return token


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("鏃у瘑鐮佷笉姝ｇ‘")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
