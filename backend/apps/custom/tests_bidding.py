from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CommissionBid, CommissionInvitation, CustomRequest


User = get_user_model()


class CommissionMarketplaceAPITests(APITestCase):
    def setUp(self):
        self.requester = User.objects.create_user(username="requester", password="test-pass-123")
        self.artist_one = User.objects.create_user(username="artist-one", password="test-pass-123")
        self.artist_two = User.objects.create_user(username="artist-two", password="test-pass-123")
        self.outsider = User.objects.create_user(username="outsider", password="test-pass-123")
        self.commission = CustomRequest.objects.create(
            requester=self.requester,
            title="Q版双人头像",
            description="需要两位角色和简单背景",
            budget=Decimal("1000.00"),
            budget_note="1000",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def bids_url(self):
        return f"/api/custom/{self.commission.pk}/bids/"

    def invitations_url(self):
        return f"/api/custom/{self.commission.pk}/invitations/"

    def bid(self, user, amount):
        self.auth(user)
        return self.client.post(self.bids_url(), {"amount": amount}, format="json")

    def invite(self, artist, amount="800.00"):
        self.auth(self.requester)
        return self.client.post(
            self.invitations_url(),
            {"artist_id": artist.pk, "amount": amount, "message": "定向合作邀请"},
            format="json",
        )

    def test_bid_upsert_withdraw_and_requester_cannot_bid(self):
        self.assertEqual(self.bid(self.artist_one, "650.00").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.bid(self.artist_one, "600.00").status_code, status.HTTP_200_OK)
        self.assertEqual(CommissionBid.objects.filter(custom_request=self.commission).count(), 1)
        bid = CommissionBid.objects.get(custom_request=self.commission)
        self.assertEqual(bid.amount, Decimal("600.00"))

        self.auth(self.artist_one)
        self.assertEqual(self.client.delete(self.bids_url()).status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, CommissionBid.Status.WITHDRAWN)
        self.assertEqual(self.bid(self.requester, "500.00").status_code, status.HTTP_400_BAD_REQUEST)

    def test_candidate_details_are_private_while_bid_count_is_public(self):
        self.bid(self.artist_one, "700.00")
        self.bid(self.artist_two, "650.00")
        self.invite(self.artist_one)
        self.invite(self.artist_two)

        self.client.force_authenticate(user=None)
        data = self.client.get(f"/api/custom/{self.commission.pk}/").data["data"]
        self.assertEqual(data["bid_count"], 2)
        self.assertEqual(data["bids"], [])
        self.assertEqual(data["invitations"], [])

        self.auth(self.outsider)
        data = self.client.get(f"/api/custom/{self.commission.pk}/").data["data"]
        self.assertEqual(data["bids"], [])
        self.assertEqual(data["invitations"], [])

        self.auth(self.artist_one)
        data = self.client.get(f"/api/custom/{self.commission.pk}/").data["data"]
        self.assertEqual([item["artist"] for item in data["bids"]], [self.artist_one.pk])
        self.assertEqual([item["artist"] for item in data["invitations"]], [self.artist_one.pk])

        self.auth(self.requester)
        data = self.client.get(f"/api/custom/{self.commission.pk}/").data["data"]
        self.assertEqual(len(data["bids"]), 2)
        self.assertEqual(len(data["invitations"]), 2)

    def test_requester_selects_bid_and_closes_other_candidates(self):
        self.bid(self.artist_one, "700.00")
        self.bid(self.artist_two, "650.00")
        self.invite(self.artist_two, "680.00")
        selected = CommissionBid.objects.get(custom_request=self.commission, artist=self.artist_one)

        self.auth(self.outsider)
        url = f"/api/custom/{self.commission.pk}/select-bid/"
        self.assertEqual(
            self.client.post(url, {"bid_id": selected.pk}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.auth(self.requester)
        self.assertEqual(
            self.client.post(url, {"bid_id": selected.pk}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.commission.refresh_from_db()
        selected.refresh_from_db()
        self.assertEqual(self.commission.artist, self.artist_one)
        self.assertEqual(self.commission.agreed_price, Decimal("700.00"))
        self.assertEqual(self.commission.selected_bid, selected)
        self.assertEqual(selected.status, CommissionBid.Status.SELECTED)
        self.assertEqual(
            CommissionBid.objects.get(custom_request=self.commission, artist=self.artist_two).status,
            CommissionBid.Status.REJECTED,
        )
        self.assertEqual(
            CommissionInvitation.objects.get(custom_request=self.commission, artist=self.artist_two).status,
            CommissionInvitation.Status.CANCELLED,
        )

    def test_declined_invitation_cannot_be_reopened_for_same_commission(self):
        self.assertEqual(self.invite(self.artist_one).status_code, status.HTTP_201_CREATED)
        invitation = CommissionInvitation.objects.get(custom_request=self.commission, artist=self.artist_one)
        url = f"/api/custom/{self.commission.pk}/respond-invitation/"

        self.auth(self.artist_two)
        self.assertEqual(
            self.client.post(
                url,
                {"invitation_id": invitation.pk, "decision": "decline"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.auth(self.artist_one)
        self.assertEqual(
            self.client.post(
                url,
                {"invitation_id": invitation.pk, "decision": "decline"},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CommissionInvitation.Status.DECLINED)
        self.assertEqual(self.invite(self.artist_one, "780.00").status_code, status.HTTP_400_BAD_REQUEST)

    def test_accepting_invitation_assigns_artist_and_abandon_reopens_cleanly(self):
        self.bid(self.artist_two, "620.00")
        self.invite(self.artist_one, "750.00")
        self.invite(self.artist_two, "700.00")
        accepted = CommissionInvitation.objects.get(custom_request=self.commission, artist=self.artist_one)
        url = f"/api/custom/{self.commission.pk}/respond-invitation/"

        self.auth(self.artist_one)
        response = self.client.post(
            url,
            {"invitation_id": accepted.pk, "decision": "accept"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.commission.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(self.commission.artist, self.artist_one)
        self.assertEqual(self.commission.agreed_price, Decimal("750.00"))
        self.assertIsNone(self.commission.selected_bid)
        self.assertEqual(accepted.status, CommissionInvitation.Status.ACCEPTED)
        self.assertEqual(
            CommissionBid.objects.get(custom_request=self.commission, artist=self.artist_two).status,
            CommissionBid.Status.REJECTED,
        )
        self.assertEqual(
            CommissionInvitation.objects.get(custom_request=self.commission, artist=self.artist_two).status,
            CommissionInvitation.Status.CANCELLED,
        )

        response = self.client.post(f"/api/custom/{self.commission.pk}/abandon/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.commission.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(self.commission.status, CustomRequest.Status.SUBMITTED)
        self.assertIsNone(self.commission.artist)
        self.assertIsNone(self.commission.agreed_price)
        self.assertIsNone(self.commission.selected_bid)
        self.assertEqual(accepted.status, CommissionInvitation.Status.CANCELLED)
