from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

<<<<<<< HEAD
=======
from .models import DirectMessage, Follow

>>>>>>> origin/group_code

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "avatar", "bio", "profile", "is_admin"]
        read_only_fields = ["id", "is_admin"]


class AdminUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        read_only_fields = ["id"]


<<<<<<< HEAD
=======
class PublicProfileSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    intro = serializers.SerializerMethodField()
    philosophy = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    creativeYears = serializers.SerializerMethodField()
    artwork_count = serializers.SerializerMethodField()
    follower_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()
    is_mutual = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "avatar",
            "bio",
            "intro",
            "philosophy",
            "skills",
            "creativeYears",
            "artwork_count",
            "follower_count",
            "following_count",
            "is_following",
            "is_followed_by",
            "is_mutual",
        ]
        read_only_fields = fields

    @staticmethod
    def _profile(obj):
        return obj.profile if isinstance(obj.profile, dict) else {}

    def get_display_name(self, obj):
        profile = self._profile(obj)
        return profile.get("displayName") or obj.get_full_name() or obj.username

    def get_avatar(self, obj):
        if obj.avatar:
            try:
                url = obj.avatar.url
                request = self.context.get("request")
                return request.build_absolute_uri(url) if request else url
            except (ValueError, OSError):
                pass
        return self._profile(obj).get("avatar", "")

    def get_intro(self, obj):
        profile = self._profile(obj)
        return profile.get("intro") or profile.get("signature") or ""

    def get_philosophy(self, obj):
        return self._profile(obj).get("philosophy", "")

    def get_skills(self, obj):
        skills = self._profile(obj).get("skills", [])
        return skills if isinstance(skills, list) else []

    def get_creativeYears(self, obj):
        return self._profile(obj).get("creativeYears", "")

    def get_artwork_count(self, obj):
        value = getattr(obj, "artwork_count", None)
        return value if value is not None else obj.artworks.count()

    def get_follower_count(self, obj):
        value = getattr(obj, "follower_count", None)
        return value if value is not None else obj.follower_relations.count()

    def get_following_count(self, obj):
        value = getattr(obj, "following_count", None)
        return value if value is not None else obj.following_relations.count()

    def get_is_following(self, obj):
        value = getattr(obj, "viewer_is_following", None)
        if value is not None:
            return bool(value)
        request = self.context.get("request")
        viewer = getattr(request, "user", None)
        return bool(
            viewer
            and viewer.is_authenticated
            and Follow.objects.filter(from_user=viewer, to_user=obj).exists()
        )

    def get_is_followed_by(self, obj):
        value = getattr(obj, "viewer_is_followed_by", None)
        if value is not None:
            return bool(value)
        request = self.context.get("request")
        viewer = getattr(request, "user", None)
        return bool(
            viewer
            and viewer.is_authenticated
            and Follow.objects.filter(from_user=obj, to_user=viewer).exists()
        )

    def get_is_mutual(self, obj):
        return self.get_is_following(obj) and self.get_is_followed_by(obj)


class DirectMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    recipient_username = serializers.CharField(source="recipient.username", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = DirectMessage
        fields = [
            "id",
            "sender",
            "sender_username",
            "recipient",
            "recipient_username",
            "body",
            "created_at",
            "read_at",
            "is_mine",
        ]
        read_only_fields = fields

    def get_is_mine(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.sender_id == request.user.id)


class DirectMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(
        max_length=DirectMessage.MAX_BODY_LENGTH,
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message body cannot be empty.")
        return value


>>>>>>> origin/group_code
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
<<<<<<< HEAD
=======
            "homeTags": [],
>>>>>>> origin/group_code
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
