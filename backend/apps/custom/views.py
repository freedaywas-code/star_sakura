from datetime import timedelta
<<<<<<< HEAD

from django.db import transaction
from django.db.models import Q
=======
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Prefetch, Q
>>>>>>> origin/group_code
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.caching import CachedPublicReadMixin
from common.response import ApiResponseMixin, ok
from common.throttling import WriteScopedThrottleMixin

<<<<<<< HEAD
from .models import CommissionOption, CustomRequest
from .serializers import CommissionOptionSerializer, CustomRequestSerializer
=======
from .models import CommissionBid, CommissionInvitation, CommissionOption, CustomRequest
from .serializers import (
    ArtistCandidateSerializer,
    CommissionBidSelectionSerializer,
    CommissionBidSerializer,
    CommissionBidUpsertSerializer,
    CommissionInvitationCreateSerializer,
    CommissionInvitationResponseSerializer,
    CommissionInvitationSerializer,
    CommissionOptionSerializer,
    CustomRequestSerializer,
)


User = get_user_model()
>>>>>>> origin/group_code


class CommissionOptionViewSet(CachedPublicReadMixin, ApiResponseMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionOptionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return CommissionOption.objects.filter(is_active=True).order_by("sort_order", "id")


class CustomRequestViewSet(CachedPublicReadMixin, WriteScopedThrottleMixin, ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = CustomRequestSerializer
    filterset_fields = ["status", "requester", "artist"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]
    ordering_fields = ["created_at", "updated_at", "budget", "progress"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
<<<<<<< HEAD
        queryset = CustomRequest.objects.select_related("requester", "artist").all()
=======
        queryset = (
            CustomRequest.objects.select_related("requester", "artist", "selected_bid__artist")
            .annotate(
                active_bid_count=Count(
                    "bids",
                    filter=Q(bids__status=CommissionBid.Status.ACTIVE),
                    distinct=True,
                )
            )
        )
>>>>>>> origin/group_code
        public_statuses = [
            CustomRequest.Status.SUBMITTED,
            CustomRequest.Status.ACCEPTED,
            CustomRequest.Status.ABANDON_REQUESTED,
        ]
        if not self.request.user.is_authenticated:
            return queryset.filter(status__in=public_statuses)
<<<<<<< HEAD
=======
        queryset = queryset.prefetch_related(
            Prefetch(
                "bids",
                queryset=CommissionBid.objects.select_related("artist").order_by("amount", "created_at"),
                to_attr="_candidate_bids",
            ),
            Prefetch(
                "invitations",
                queryset=CommissionInvitation.objects.select_related("artist", "invited_by").order_by("-created_at"),
                to_attr="_candidate_invitations",
            ),
        )
>>>>>>> origin/group_code
        if self.request.user.is_admin:
            return queryset
        return queryset.filter(
            Q(status__in=public_statuses)
            | Q(requester=self.request.user)
            | Q(artist=self.request.user)
<<<<<<< HEAD
        )
=======
            | Q(bids__artist=self.request.user)
            | Q(invitations__artist=self.request.user)
        ).distinct()
>>>>>>> origin/group_code

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user, status=CustomRequest.Status.SUBMITTED)

    def _ensure_requester_or_admin(self, custom_request):
        if self.request.user.is_admin or custom_request.requester_id == self.request.user.id:
            return
        raise PermissionDenied("Only the requester or admin can modify this commission.")

    def _ensure_artist_or_admin(self, custom_request):
        if self.request.user.is_admin or custom_request.artist_id == self.request.user.id:
            return
        raise PermissionDenied("Only the artist or admin can update this commission.")

<<<<<<< HEAD
    def perform_update(self, serializer):
        custom_request = self.get_object()
        self._ensure_requester_or_admin(custom_request)
        if custom_request.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("Accepted commissions cannot be edited.")
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_requester_or_admin(instance)
        if instance.status != CustomRequest.Status.SUBMITTED:
            raise ValidationError("Accepted commissions cannot be deleted.")
        instance.delete()
=======
    @staticmethod
    def _ensure_open(custom_request):
        if (
            custom_request.status != CustomRequest.Status.SUBMITTED
            or custom_request.artist_id
            or custom_request.selected_bid_id
            or custom_request.agreed_price is not None
        ):
            raise ValidationError("This commission is no longer open.")

    @staticmethod
    def _locked_custom_request(pk):
        return get_object_or_404(CustomRequest.objects.select_for_update(), pk=pk)

    @staticmethod
    def _lock_candidates(custom_request):
        bids = list(
            CommissionBid.objects.select_for_update()
            .select_related("artist")
            .filter(custom_request=custom_request)
            .order_by("pk")
        )
        invitations = list(
            CommissionInvitation.objects.select_for_update()
            .select_related("artist", "invited_by")
            .filter(custom_request=custom_request)
            .order_by("pk")
        )
        return bids, invitations

    @staticmethod
    def _assign_artist(custom_request, artist, agreed_price, bids, invitations, selected_bid=None, invitation=None):
        now = timezone.now()
        changed_bids = []
        for bid in bids:
            next_status = (
                CommissionBid.Status.SELECTED
                if selected_bid is not None and bid.pk == selected_bid.pk
                else CommissionBid.Status.REJECTED
                if bid.status == CommissionBid.Status.ACTIVE
                else bid.status
            )
            if next_status != bid.status:
                bid.status = next_status
                bid.updated_at = now
                changed_bids.append(bid)
        if changed_bids:
            CommissionBid.objects.bulk_update(changed_bids, ["status", "updated_at"])

        changed_invitations = []
        for item in invitations:
            if invitation is not None and item.pk == invitation.pk:
                item.status = CommissionInvitation.Status.ACCEPTED
                item.responded_at = now
                item.updated_at = now
                changed_invitations.append(item)
            elif item.status == CommissionInvitation.Status.PENDING:
                item.status = CommissionInvitation.Status.CANCELLED
                item.responded_at = now
                item.updated_at = now
                changed_invitations.append(item)
        if changed_invitations:
            CommissionInvitation.objects.bulk_update(
                changed_invitations,
                ["status", "responded_at", "updated_at"],
            )

        custom_request.artist = artist
        custom_request.status = CustomRequest.Status.ACCEPTED
        custom_request.progress = max(custom_request.progress, 10)
        custom_request.accepted_at = now
        custom_request.abandon_requested_at = None
        custom_request.agreed_price = agreed_price
        custom_request.selected_bid = selected_bid
        custom_request.save(
            update_fields=[
                "artist",
                "status",
                "progress",
                "accepted_at",
                "abandon_requested_at",
                "agreed_price",
                "selected_bid",
                "updated_at",
            ]
        )

    @staticmethod
    def _reopen_commission(custom_request, bids, invitations):
        now = timezone.now()
        selected_bids = []
        for bid in bids:
            if bid.status == CommissionBid.Status.SELECTED:
                bid.status = CommissionBid.Status.WITHDRAWN
                bid.updated_at = now
                selected_bids.append(bid)
        if selected_bids:
            CommissionBid.objects.bulk_update(selected_bids, ["status", "updated_at"])

        accepted_invitations = []
        for invitation in invitations:
            if invitation.status == CommissionInvitation.Status.ACCEPTED:
                invitation.status = CommissionInvitation.Status.CANCELLED
                invitation.responded_at = now
                invitation.updated_at = now
                accepted_invitations.append(invitation)
        if accepted_invitations:
            CommissionInvitation.objects.bulk_update(
                accepted_invitations,
                ["status", "responded_at", "updated_at"],
            )

        custom_request.artist = None
        custom_request.status = CustomRequest.Status.SUBMITTED
        custom_request.progress = 0
        custom_request.accepted_at = None
        custom_request.abandon_requested_at = None
        custom_request.agreed_price = None
        custom_request.selected_bid = None
        custom_request.save(
            update_fields=[
                "artist",
                "status",
                "progress",
                "accepted_at",
                "abandon_requested_at",
                "agreed_price",
                "selected_bid",
                "updated_at",
            ]
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        with transaction.atomic():
            custom_request = self._locked_custom_request(kwargs.get("pk"))
            self._ensure_requester_or_admin(custom_request)
            self._ensure_open(custom_request)
            serializer = self.get_serializer(custom_request, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return ok(serializer.data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            custom_request = self._locked_custom_request(kwargs.get("pk"))
            self._ensure_requester_or_admin(custom_request)
            self._ensure_open(custom_request)
            custom_request.delete()
        return ok(None, status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def artists(self, request):
        search = str(request.query_params.get("search", "")).strip()[:100]
        try:
            page_size = int(request.query_params.get("page_size", 20))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page_size": "Page size must be a number."}) from exc
        page_size = min(max(page_size, 1), 50)
        queryset = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(bio__icontains=search)
            )
        queryset = queryset.order_by("username", "id")[:page_size]
        return ok(ArtistCandidateSerializer(queryset, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get", "post", "delete"])
    def bids(self, request, pk=None):
        if request.method == "GET":
            custom_request = self.get_object()
            queryset = CommissionBid.objects.select_related("artist").filter(custom_request=custom_request)
            if not (request.user.is_admin or custom_request.requester_id == request.user.id):
                queryset = queryset.filter(artist=request.user)
            return ok(CommissionBidSerializer(queryset, many=True, context={"request": request}).data)

        if request.method == "POST":
            input_serializer = CommissionBidUpsertSerializer(data=request.data)
            input_serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                custom_request = self._locked_custom_request(pk)
                self._ensure_open(custom_request)
                if custom_request.requester_id == request.user.id:
                    raise ValidationError("You cannot bid on your own commission.")
                bid = (
                    CommissionBid.objects.select_for_update()
                    .filter(custom_request=custom_request, artist=request.user)
                    .first()
                )
                created = bid is None
                if bid is None:
                    bid = CommissionBid(
                        custom_request=custom_request,
                        artist=request.user,
                    )
                bid.amount = input_serializer.validated_data["amount"]
                bid.message = input_serializer.validated_data.get("message", "")
                bid.status = CommissionBid.Status.ACTIVE
                bid.save()
            return ok(
                CommissionBidSerializer(bid, context={"request": request}).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        with transaction.atomic():
            custom_request = self._locked_custom_request(pk)
            bid = get_object_or_404(
                CommissionBid.objects.select_for_update(),
                custom_request=custom_request,
                artist=request.user,
            )
            if bid.status == CommissionBid.Status.SELECTED:
                raise ValidationError("A selected bid must be released through the abandon flow.")
            if bid.status != CommissionBid.Status.ACTIVE:
                raise ValidationError("This bid is not active.")
            self._ensure_open(custom_request)
            bid.status = CommissionBid.Status.WITHDRAWN
            bid.save(update_fields=["status", "updated_at"])
        return ok(CommissionBidSerializer(bid, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="select-bid")
    def select_bid(self, request, pk=None):
        input_serializer = CommissionBidSelectionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            custom_request = self._locked_custom_request(pk)
            self._ensure_requester_or_admin(custom_request)
            self._ensure_open(custom_request)
            bids, invitations = self._lock_candidates(custom_request)
            selected_bid = next(
                (bid for bid in bids if bid.pk == input_serializer.validated_data["bid_id"]),
                None,
            )
            if selected_bid is None:
                raise ValidationError({"bid_id": "This bid does not belong to the commission."})
            if selected_bid.status != CommissionBid.Status.ACTIVE:
                raise ValidationError({"bid_id": "Only an active bid can be selected."})
            self._assign_artist(
                custom_request,
                selected_bid.artist,
                selected_bid.amount,
                bids,
                invitations,
                selected_bid=selected_bid,
            )
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["get", "post"])
    def invitations(self, request, pk=None):
        if request.method == "GET":
            custom_request = self.get_object()
            queryset = CommissionInvitation.objects.select_related("artist", "invited_by").filter(
                custom_request=custom_request
            )
            if not (request.user.is_admin or custom_request.requester_id == request.user.id):
                queryset = queryset.filter(artist=request.user)
            return ok(CommissionInvitationSerializer(queryset, many=True, context={"request": request}).data)

        input_serializer = CommissionInvitationCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            custom_request = self._locked_custom_request(pk)
            self._ensure_requester_or_admin(custom_request)
            self._ensure_open(custom_request)
            artist = (
                User.objects.select_for_update()
                .filter(pk=input_serializer.validated_data["artist"].pk, is_active=True)
                .first()
            )
            if artist is None:
                raise ValidationError({"artist_id": "This artist is not available."})
            if artist.pk in {custom_request.requester_id, request.user.id}:
                raise ValidationError({"artist_id": "You cannot invite yourself to this commission."})
            amount = input_serializer.validated_data.get("amount")
            if amount is None:
                amount = custom_request.budget if custom_request.budget > Decimal("0") else None
            if amount is None:
                raise ValidationError({"amount": "A positive invitation price is required."})
            invitation = (
                CommissionInvitation.objects.select_for_update()
                .filter(custom_request=custom_request, artist=artist)
                .first()
            )
            created = invitation is None
            if invitation is not None and invitation.status == CommissionInvitation.Status.DECLINED:
                raise ValidationError(
                    {"artist_id": "This artist has declined the invitation for this commission."}
                )
            if invitation is None:
                invitation = CommissionInvitation(
                    custom_request=custom_request,
                    artist=artist,
                )
            invitation.invited_by = request.user
            invitation.amount = amount
            invitation.message = input_serializer.validated_data.get("message", "")
            invitation.status = CommissionInvitation.Status.PENDING
            invitation.responded_at = None
            invitation.save()
        return ok(
            CommissionInvitationSerializer(invitation, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="respond-invitation")
    def respond_invitation(self, request, pk=None):
        input_serializer = CommissionInvitationResponseSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            custom_request = self._locked_custom_request(pk)
            bids, invitations = self._lock_candidates(custom_request)
            invitation = next(
                (
                    item
                    for item in invitations
                    if item.pk == input_serializer.validated_data["invitation_id"]
                ),
                None,
            )
            if invitation is None:
                raise ValidationError({"invitation_id": "This invitation does not belong to the commission."})
            if not (request.user.is_admin or invitation.artist_id == request.user.id):
                raise PermissionDenied("Only the invited artist can respond to this invitation.")
            if invitation.status != CommissionInvitation.Status.PENDING:
                raise ValidationError("This invitation has already been answered or cancelled.")
            decision = input_serializer.validated_data["decision"]
            if decision == "decline":
                invitation.status = CommissionInvitation.Status.DECLINED
                invitation.responded_at = timezone.now()
                invitation.save(update_fields=["status", "responded_at", "updated_at"])
                return ok(CommissionInvitationSerializer(invitation, context={"request": request}).data)

            self._ensure_open(custom_request)
            self._assign_artist(
                custom_request,
                invitation.artist,
                invitation.amount,
                bids,
                invitations,
                invitation=invitation,
            )
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
>>>>>>> origin/group_code

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        with transaction.atomic():
<<<<<<< HEAD
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if custom_request.requester_id == request.user.id:
                raise ValidationError("You cannot accept your own commission.")
            if custom_request.status != CustomRequest.Status.SUBMITTED or custom_request.artist_id:
                raise ValidationError("This commission has already been accepted.")
            custom_request.artist = request.user
            custom_request.status = CustomRequest.Status.ACCEPTED
            custom_request.progress = max(custom_request.progress, 10)
            custom_request.accepted_at = timezone.now()
            custom_request.abandon_requested_at = None
            custom_request.save(update_fields=["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"])
=======
            custom_request = self._locked_custom_request(pk)
            self._ensure_open(custom_request)
            bids, invitations = self._lock_candidates(custom_request)
            invitation = next(
                (
                    item
                    for item in invitations
                    if item.artist_id == request.user.id
                    and item.status == CommissionInvitation.Status.PENDING
                ),
                None,
            )
            if invitation is None:
                raise ValidationError(
                    "Direct acceptance is disabled. Submit a bid or accept a pending invitation."
                )
            self._assign_artist(
                custom_request,
                invitation.artist,
                invitation.amount,
                bids,
                invitations,
                invitation=invitation,
            )
>>>>>>> origin/group_code
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def abandon(self, request, pk=None):
        with transaction.atomic():
<<<<<<< HEAD
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
=======
            custom_request = self._locked_custom_request(pk)
>>>>>>> origin/group_code
            self._ensure_artist_or_admin(custom_request)
            if custom_request.status != CustomRequest.Status.ACCEPTED:
                raise ValidationError("This commission cannot be abandoned now.")

            accepted_at = custom_request.accepted_at or custom_request.updated_at
            if accepted_at and timezone.now() - accepted_at <= timedelta(hours=1):
<<<<<<< HEAD
                custom_request.artist = None
                custom_request.status = CustomRequest.Status.SUBMITTED
                custom_request.progress = 0
                custom_request.accepted_at = None
                custom_request.abandon_requested_at = None
                update_fields = ["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"]
            else:
                custom_request.status = CustomRequest.Status.ABANDON_REQUESTED
                custom_request.abandon_requested_at = timezone.now()
                update_fields = ["status", "abandon_requested_at", "updated_at"]

            custom_request.save(update_fields=update_fields)
=======
                bids, invitations = self._lock_candidates(custom_request)
                self._reopen_commission(custom_request, bids, invitations)
            else:
                custom_request.status = CustomRequest.Status.ABANDON_REQUESTED
                custom_request.abandon_requested_at = timezone.now()
                custom_request.save(update_fields=["status", "abandon_requested_at", "updated_at"])

>>>>>>> origin/group_code
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def resolve_abandon(self, request, pk=None):
        with transaction.atomic():
<<<<<<< HEAD
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
=======
            custom_request = self._locked_custom_request(pk)
>>>>>>> origin/group_code
            self._ensure_requester_or_admin(custom_request)
            if custom_request.status != CustomRequest.Status.ABANDON_REQUESTED:
                raise ValidationError("There is no pending abandon request.")

            approved = request.data.get("approved", True)
            approved = approved is True or str(approved).lower() in {"1", "true", "yes", "on"}
            if approved:
<<<<<<< HEAD
                custom_request.artist = None
                custom_request.status = CustomRequest.Status.SUBMITTED
                custom_request.progress = 0
                custom_request.accepted_at = None
                update_fields = ["artist", "status", "progress", "accepted_at", "abandon_requested_at", "updated_at"]
            else:
                custom_request.status = CustomRequest.Status.ACCEPTED
                update_fields = ["status", "abandon_requested_at", "updated_at"]
            custom_request.abandon_requested_at = None
            custom_request.save(update_fields=update_fields)
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data, status=status.HTTP_200_OK)
=======
                bids, invitations = self._lock_candidates(custom_request)
                self._reopen_commission(custom_request, bids, invitations)
            else:
                custom_request.status = CustomRequest.Status.ACCEPTED
                custom_request.abandon_requested_at = None
                custom_request.save(update_fields=["status", "abandon_requested_at", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
>>>>>>> origin/group_code

    @action(detail=True, methods=["post"])
    def set_progress(self, request, pk=None):
        with transaction.atomic():
<<<<<<< HEAD
            custom_request = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            self._ensure_artist_or_admin(custom_request)
=======
            custom_request = self._locked_custom_request(pk)
            self._ensure_artist_or_admin(custom_request)
            if custom_request.status not in {
                CustomRequest.Status.ACCEPTED,
                CustomRequest.Status.IN_PROGRESS,
                CustomRequest.Status.REVIEWING,
            }:
                raise ValidationError("This commission cannot be progressed now.")
>>>>>>> origin/group_code
            try:
                progress = int(request.data.get("progress", custom_request.progress))
            except (TypeError, ValueError) as exc:
                raise ValidationError({"progress": "Progress must be a number."}) from exc
            status_value = request.data.get("status", custom_request.status)
<<<<<<< HEAD
            if status_value == "open":
                status_value = CustomRequest.Status.SUBMITTED
            if not 0 <= progress <= 100:
                raise ValidationError({"progress": "Progress must be between 0 and 100."})
            if status_value not in CustomRequest.Status.values:
                raise ValidationError({"status": "Invalid commission status."})
=======
            if not 0 <= progress <= 100:
                raise ValidationError({"progress": "Progress must be between 0 and 100."})
            allowed_statuses = {
                CustomRequest.Status.ACCEPTED,
                CustomRequest.Status.IN_PROGRESS,
                CustomRequest.Status.REVIEWING,
                CustomRequest.Status.COMPLETED,
            }
            if status_value not in allowed_statuses:
                raise ValidationError({"status": "Invalid commission status transition."})
>>>>>>> origin/group_code
            custom_request.progress = progress
            custom_request.status = status_value
            custom_request.save(update_fields=["progress", "status", "updated_at"])
        return ok(CustomRequestSerializer(custom_request, context={"request": request}).data)
