from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import CommissionBid, CommissionInvitation, CommissionOption, CustomRequest


User = get_user_model()


class ArtistCandidateSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "avatar", "bio", "profile"]
        read_only_fields = fields

    def get_display_name(self, obj):
        profile = obj.profile if isinstance(obj.profile, dict) else {}
        return profile.get("displayName") or obj.get_full_name() or obj.username

    def get_profile(self, obj):
        profile = obj.profile if isinstance(obj.profile, dict) else {}
        return {
            "displayName": profile.get("displayName") or obj.get_full_name() or obj.username,
            "avatar": profile.get("avatar", ""),
            "skills": profile.get("skills", []),
        }


class CommissionBidSerializer(serializers.ModelSerializer):
    artist_username = serializers.CharField(source="artist.username", read_only=True)
    artist_avatar = serializers.ImageField(source="artist.avatar", read_only=True)

    class Meta:
        model = CommissionBid
        fields = [
            "id",
            "custom_request",
            "artist",
            "artist_username",
            "artist_avatar",
            "amount",
            "message",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CommissionInvitationSerializer(serializers.ModelSerializer):
    artist_username = serializers.CharField(source="artist.username", read_only=True)
    artist_avatar = serializers.ImageField(source="artist.avatar", read_only=True)
    invited_by_username = serializers.CharField(source="invited_by.username", read_only=True)

    class Meta:
        model = CommissionInvitation
        fields = [
            "id",
            "custom_request",
            "artist",
            "artist_username",
            "artist_avatar",
            "invited_by",
            "invited_by_username",
            "amount",
            "message",
            "status",
            "responded_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CommissionBidUpsertSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class CommissionBidSelectionSerializer(serializers.Serializer):
    bid_id = serializers.IntegerField(min_value=1)


class CommissionInvitationCreateSerializer(serializers.Serializer):
    artist_id = serializers.PrimaryKeyRelatedField(
        source="artist",
        queryset=User.objects.filter(is_active=True),
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class CommissionInvitationResponseSerializer(serializers.Serializer):
    invitation_id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=["accept", "decline"])


class CustomRequestSerializer(serializers.ModelSerializer):
    requester_username = serializers.CharField(source="requester.username", read_only=True)
    artist_username = serializers.CharField(source="artist.username", read_only=True)
    budget = serializers.CharField(required=False, allow_blank=True)
    agreed_price = serializers.SerializerMethodField()
    bid_count = serializers.SerializerMethodField()
    bids = serializers.SerializerMethodField()
    invitations = serializers.SerializerMethodField()
    my_bid = serializers.SerializerMethodField()
    my_invitation = serializers.SerializerMethodField()
    selected_bid = serializers.SerializerMethodField()

    class Meta:
        model = CustomRequest
        fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "title",
            "type_label",
            "description",
            "reference_image",
            "budget",
            "status",
            "progress",
            "accepted_at",
            "abandon_requested_at",
            "agreed_price",
            "bid_count",
            "bids",
            "invitations",
            "my_bid",
            "my_invitation",
            "selected_bid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "status",
            "progress",
            "accepted_at",
            "abandon_requested_at",
            "agreed_price",
            "bid_count",
            "bids",
            "invitations",
            "my_bid",
            "my_invitation",
            "selected_bid",
            "created_at",
            "updated_at",
        ]

    def _request_user(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def _can_view_all_candidates(self, instance):
        user = self._request_user()
        return bool(user and (getattr(user, "is_admin", False) or instance.requester_id == user.id))

    def _visible_bids(self, instance):
        user = self._request_user()
        if not user:
            return []
        cached = getattr(instance, "_serializer_visible_bids", None)
        if cached is not None and cached[0] == user.id:
            return cached[1]
        prefetched = getattr(instance, "_candidate_bids", None)
        if prefetched is None:
            queryset = instance.bids.select_related("artist")
            if not self._can_view_all_candidates(instance):
                queryset = queryset.filter(artist=user)
            visible = list(queryset)
        elif self._can_view_all_candidates(instance):
            visible = list(prefetched)
        else:
            visible = [bid for bid in prefetched if bid.artist_id == user.id]
        instance._serializer_visible_bids = (user.id, visible)
        return visible

    def _visible_invitations(self, instance):
        user = self._request_user()
        if not user:
            return []
        cached = getattr(instance, "_serializer_visible_invitations", None)
        if cached is not None and cached[0] == user.id:
            return cached[1]
        prefetched = getattr(instance, "_candidate_invitations", None)
        if prefetched is None:
            queryset = instance.invitations.select_related("artist", "invited_by")
            if not self._can_view_all_candidates(instance):
                queryset = queryset.filter(artist=user)
            visible = list(queryset)
        elif self._can_view_all_candidates(instance):
            visible = list(prefetched)
        else:
            visible = [invitation for invitation in prefetched if invitation.artist_id == user.id]
        instance._serializer_visible_invitations = (user.id, visible)
        return visible

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["budget"] = instance.budget_note or str(instance.budget)
        data["status"] = "open" if instance.status == CustomRequest.Status.SUBMITTED else instance.status
        return data

    def get_agreed_price(self, instance):
        user = self._request_user()
        if not user or not (
            getattr(user, "is_admin", False)
            or instance.requester_id == user.id
            or instance.artist_id == user.id
        ):
            return None
        return str(instance.agreed_price) if instance.agreed_price is not None else None

    def get_bid_count(self, instance):
        annotated_count = getattr(instance, "active_bid_count", None)
        if annotated_count is not None:
            return annotated_count
        return instance.bids.filter(status=CommissionBid.Status.ACTIVE).count()

    def get_bids(self, instance):
        return CommissionBidSerializer(
            self._visible_bids(instance),
            many=True,
            context=self.context,
        ).data

    def get_invitations(self, instance):
        return CommissionInvitationSerializer(
            self._visible_invitations(instance),
            many=True,
            context=self.context,
        ).data

    def get_my_bid(self, instance):
        user = self._request_user()
        if not user:
            return None
        bid = next((item for item in self._visible_bids(instance) if item.artist_id == user.id), None)
        return CommissionBidSerializer(bid, context=self.context).data if bid else None

    def get_my_invitation(self, instance):
        user = self._request_user()
        if not user:
            return None
        invitation = next(
            (item for item in self._visible_invitations(instance) if item.artist_id == user.id),
            None,
        )
        return CommissionInvitationSerializer(invitation, context=self.context).data if invitation else None

    def get_selected_bid(self, instance):
        user = self._request_user()
        if not user or instance.selected_bid_id is None:
            return None
        if not (
            getattr(user, "is_admin", False)
            or instance.requester_id == user.id
            or instance.artist_id == user.id
        ):
            return None
        return CommissionBidSerializer(instance.selected_bid, context=self.context).data

    def _apply_budget(self, validated_data):
        if "budget" not in validated_data:
            return validated_data
        budget_text = str(validated_data.pop("budget", "") or "").strip()
        validated_data["budget_note"] = budget_text
        try:
            validated_data["budget"] = Decimal(budget_text) if budget_text else Decimal("0")
        except (InvalidOperation, ValueError):
            validated_data["budget"] = Decimal("0")
        return validated_data

    def create(self, validated_data):
        return super().create(self._apply_budget(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._apply_budget(validated_data))


class CommissionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionOption
        fields = ["code", "title", "price_label", "sort_order"]


class ArtistRecommendationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    avatar = serializers.CharField(allow_blank=True)
    bio = serializers.CharField(allow_blank=True)
    skills = serializers.ListField(child=serializers.CharField())


class SampleWorkSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    image = serializers.CharField(allow_blank=True)
    category = serializers.CharField()


class PriceRangeSerializer(serializers.Serializer):
    min = serializers.FloatField()
    max = serializers.FloatField()


class RecommendationResultSerializer(serializers.Serializer):
    artist = ArtistRecommendationSerializer()
    confidence = serializers.IntegerField()
    reason = serializers.CharField()
    sample_works = SampleWorkSerializer(many=True)
    price_range = PriceRangeSerializer()


class AIMatchResultSerializer(serializers.Serializer):
    custom_request_id = serializers.IntegerField()
    recommendations = RecommendationResultSerializer(many=True)
    total_candidates = serializers.IntegerField()
    matched_at = serializers.DateTimeField()
    used_fallback = serializers.BooleanField(default=False)
