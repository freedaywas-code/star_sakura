from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import BooleanField, Case, Count, Exists, F, IntegerField, Max, OuterRef, Q, Value, When
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from common.pagination import StandardResultsSetPagination
from common.response import ApiResponseMixin, fail, ok

from .models import DirectMessage, Follow
from .permissions import IsAdmin
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    DirectMessageCreateSerializer,
    DirectMessageSerializer,
    PublicProfileSerializer,
    RegisterSerializer,
    UserSerializer,
)


User = get_user_model()
MESSAGE_LIMIT = 3


def _profile_queryset(viewer=None):
    queryset = User.objects.annotate(
        artwork_count=Count("artworks", distinct=True),
        follower_count=Count(
            "follower_relations",
            filter=Q(follower_relations__from_user__is_active=True),
            distinct=True,
        ),
        following_count=Count(
            "following_relations",
            filter=Q(following_relations__to_user__is_active=True),
            distinct=True,
        ),
    )
    if viewer is not None and viewer.is_authenticated:
        queryset = queryset.annotate(
            viewer_is_following=Exists(
                Follow.objects.filter(from_user_id=viewer.pk, to_user_id=OuterRef("pk"))
            ),
            viewer_is_followed_by=Exists(
                Follow.objects.filter(from_user_id=OuterRef("pk"), to_user_id=viewer.pk)
            ),
        )
    else:
        queryset = queryset.annotate(
            viewer_is_following=Value(False, output_field=BooleanField()),
            viewer_is_followed_by=Value(False, output_field=BooleanField()),
        )
    return queryset


def _resolve_user(identifier, queryset=None):
    queryset = queryset if queryset is not None else User.objects.all()
    value = str(identifier).strip()
    if not value:
        raise NotFound("User not found.")

    # Usernames take precedence so a numeric username remains addressable.
    user = queryset.filter(username=value).first()
    if user is not None:
        return user
    if value.isdigit():
        user = queryset.filter(pk=int(value)).first()
        if user is not None:
            return user
    user = queryset.filter(username__iexact=value).first()
    if user is None:
        raise NotFound("User not found.")
    return user


def _lock_user_pair(first_id, second_id):
    ids = sorted({int(first_id), int(second_id)})
    users = list(User.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(users) != len(ids):
        raise NotFound("User not found.")
    return {user.pk: user for user in users}


def _is_mutual_follow(first, second):
    return (
        Follow.objects.filter(from_user=first, to_user=second).exists()
        and Follow.objects.filter(from_user=second, to_user=first).exists()
    )


def _messaging_state(sender, recipient, sent_count=None):
    unlimited = _is_mutual_follow(sender, recipient)
    if unlimited:
        return {
            "unlimited": True,
            "remaining_messages": None,
            "message_limit": MESSAGE_LIMIT,
        }
    if sent_count is None:
        sent_count = DirectMessage.objects.filter(sender=sender, recipient=recipient).count()
    return {
        "unlimited": False,
        "remaining_messages": max(0, MESSAGE_LIMIT - sent_count),
        "message_limit": MESSAGE_LIMIT,
    }


def _profile_data(user, request):
    return PublicProfileSerializer(user, context={"request": request}).data


def _pagination_data(paginator, results):
    return {
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": results,
    }


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


class PublicProfileView(ApiResponseMixin, APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, identifier):
        user = _resolve_user(
            identifier,
            _profile_queryset(request.user).filter(is_active=True),
        )
        return ok(_profile_data(user, request))


class FollowView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _target(self, request, identifier):
        target = _resolve_user(identifier, User.objects.filter(is_active=True))
        if target.pk == request.user.pk:
            raise ValidationError({"target": "You cannot follow yourself."})
        return target

    def post(self, request, identifier):
        target = self._target(request, identifier)
        with transaction.atomic():
            locked = _lock_user_pair(request.user.pk, target.pk)
            follower = locked[request.user.pk]
            target = locked[target.pk]
            if not target.is_active:
                raise ValidationError({"target": "This account is unavailable."})
            _, created = Follow.objects.get_or_create(from_user=follower, to_user=target)

        target = _profile_queryset(request.user).get(pk=target.pk)
        data = _profile_data(target, request)
        data["created"] = created
        return ok(
            data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, identifier):
        target = self._target(request, identifier)
        with transaction.atomic():
            locked = _lock_user_pair(request.user.pk, target.pk)
            follower = locked[request.user.pk]
            target = locked[target.pk]
            deleted, _ = Follow.objects.filter(from_user=follower, to_user=target).delete()

        target = _profile_queryset(request.user).get(pk=target.pk)
        data = _profile_data(target, request)
        data["removed"] = bool(deleted)
        return ok(data)


class RelationshipListView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    relation = None

    def get_queryset(self, request):
        queryset = _profile_queryset(request.user).filter(is_active=True)
        if self.relation == "followers":
            return queryset.filter(following_relations__to_user=request.user).order_by(
                "-following_relations__created_at",
                "-pk",
            )
        return queryset.filter(follower_relations__from_user=request.user).order_by(
            "-follower_relations__created_at",
            "-pk",
        )

    def get(self, request):
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(self.get_queryset(request), request, view=self)
        serializer = PublicProfileSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class FollowersView(RelationshipListView):
    relation = "followers"


class FollowingView(RelationshipListView):
    relation = "following"


class ConversationListView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        partner_rows = (
            DirectMessage.objects.filter(Q(sender=request.user) | Q(recipient=request.user))
            .annotate(
                partner_id=Case(
                    When(sender=request.user, then=F("recipient_id")),
                    default=F("sender_id"),
                    output_field=IntegerField(),
                )
            )
            .values("partner_id")
            .annotate(last_message_at=Max("created_at"))
            .order_by("-last_message_at", "-partner_id")
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(partner_rows, request, view=self)
        partner_ids = [row["partner_id"] for row in page]
        partners = {
            user.pk: user
            for user in _profile_queryset(request.user).filter(pk__in=partner_ids)
        }

        results = []
        for row in page:
            partner = partners.get(row["partner_id"])
            if partner is None:
                continue
            pair_filter = Q(sender=request.user, recipient=partner) | Q(
                sender=partner,
                recipient=request.user,
            )
            last_message = (
                DirectMessage.objects.select_related("sender", "recipient")
                .filter(pair_filter)
                .order_by("-created_at", "-id")
                .first()
            )
            last_data = DirectMessageSerializer(last_message, context={"request": request}).data
            results.append(
                {
                    "user": _profile_data(partner, request),
                    "last_message": last_data,
                    "last_message_at": last_data["created_at"],
                    "unread_count": DirectMessage.objects.filter(
                        sender=partner,
                        recipient=request.user,
                        read_at__isnull=True,
                    ).count(),
                    **_messaging_state(request.user, partner),
                }
            )
        data = _pagination_data(paginator, results)
        data["total_unread_count"] = DirectMessage.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
        ).count()
        return ok(data)


class MessageHistoryView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _partner(self, request, identifier, require_active=False):
        partner = _resolve_user(identifier)
        if partner.pk == request.user.pk:
            raise ValidationError({"recipient": "You cannot message yourself."})
        if require_active and not partner.is_active:
            raise ValidationError({"recipient": "This account is unavailable."})
        return partner

    def get(self, request, identifier):
        partner = self._partner(request, identifier)
        queryset = (
            DirectMessage.objects.select_related("sender", "recipient")
            .filter(
                Q(sender=request.user, recipient=partner)
                | Q(sender=partner, recipient=request.user)
            )
            .order_by("-created_at", "-id")
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        # Page 1 contains the latest messages; each page is returned oldest-to-newest.
        messages = DirectMessageSerializer(
            list(reversed(page)),
            many=True,
            context={"request": request},
        ).data
        profile = _profile_queryset(request.user).get(pk=partner.pk)
        return ok(
            {
                "user": _profile_data(profile, request),
                "messages": _pagination_data(paginator, messages),
                **_messaging_state(request.user, partner),
            }
        )

    def post(self, request, identifier):
        partner = self._partner(request, identifier, require_active=True)
        serializer = DirectMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = _lock_user_pair(request.user.pk, partner.pk)
            sender = locked[request.user.pk]
            recipient = locked[partner.pk]
            if not recipient.is_active:
                raise ValidationError({"recipient": "This account is unavailable."})
            unlimited = _is_mutual_follow(sender, recipient)
            sent_count = DirectMessage.objects.filter(sender=sender, recipient=recipient).count()
            if not unlimited and sent_count >= MESSAGE_LIMIT:
                return fail(
                    message=(
                        "You can send at most 3 messages in this direction until you both follow each other."
                    ),
                    code=status.HTTP_403_FORBIDDEN,
                    data={
                        "unlimited": False,
                        "remaining_messages": 0,
                        "message_limit": MESSAGE_LIMIT,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            message = DirectMessage.objects.create(
                sender=sender,
                recipient=recipient,
                body=serializer.validated_data["body"],
            )
            state = (
                {
                    "unlimited": True,
                    "remaining_messages": None,
                    "message_limit": MESSAGE_LIMIT,
                }
                if unlimited
                else {
                    "unlimited": False,
                    "remaining_messages": max(0, MESSAGE_LIMIT - sent_count - 1),
                    "message_limit": MESSAGE_LIMIT,
                }
            )

        return ok(
            {
                "message": DirectMessageSerializer(message, context={"request": request}).data,
                **state,
            },
            status=status.HTTP_201_CREATED,
        )


class MarkMessagesReadView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        sender = _resolve_user(identifier)
        if sender.pk == request.user.pk:
            raise ValidationError({"sender": "You cannot mark a conversation with yourself."})
        read_at = timezone.now()
        read_count = DirectMessage.objects.filter(
            sender=sender,
            recipient=request.user,
            read_at__isnull=True,
        ).update(read_at=read_at)
        return ok(
            {
                "read_count": read_count,
                "read_at": read_at,
            }
        )


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
