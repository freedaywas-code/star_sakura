from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.artworks.models import Artwork
from apps.custom.models import CommissionBid, CommissionInvitation, CustomRequest

from .commission_matching import (
    extract_commission_reference,
    matching_artists_for_owned_commission,
    matching_open_commissions,
    owned_open_commission,
)


User = get_user_model()


class CommissionMatchingServiceTests(TestCase):
    def setUp(self):
        self.artist = User.objects.create_user(
            username="ink-artist",
            email="artist@example.test",
            profile={
                "displayName": "水墨画师",
                "skills": ["古风", "水墨"],
                "homeTags": ["国风"],
            },
        )
        Artwork.objects.create(
            owner=self.artist,
            title="山河水墨",
            description="公开作品",
            category="古风",
            tags=["水墨", "国风"],
            price=Decimal("88.00"),
            is_available=True,
        )
        self.requester = User.objects.create_user(username="requester")

    def commission(self, **overrides):
        values = {
            "requester": self.requester,
            "title": "古风双人头像",
            "type_label": "古风头像",
            "description": "需要水墨质感和国风背景",
            "budget": Decimal("800.00"),
            "budget_note": "800 元左右",
        }
        values.update(overrides)
        return CustomRequest.objects.create(**values)

    def test_open_commission_matching_enforces_state_owner_budget_and_relevance(self):
        matching = self.commission()
        self.commission(title="现代建筑图", type_label="建筑", description="写实高楼")
        self.commission(title="低价古风", budget=Decimal("200.00"))
        self.commission(
            title="已接古风",
            status=CustomRequest.Status.ACCEPTED,
            artist=self.artist,
            agreed_price=Decimal("600.00"),
        )
        self.commission(
            requester=self.artist,
            title="自己的古风委托",
        )
        inactive_requester = User.objects.create_user(username="inactive-owner", is_active=False)
        self.commission(requester=inactive_requester, title="停用用户古风委托")

        results = matching_open_commissions(
            self.artist,
            query_terms=["古风"],
            min_budget="500",
        )

        self.assertEqual([item["id"] for item in results], [matching.id])
        self.assertEqual(results[0]["status"], CustomRequest.Status.SUBMITTED)
        self.assertNotIn("agreed_price", results[0])
        self.assertNotIn("selected_bid", results[0])
        self.assertNotIn("requester", results[0])

    def test_matching_commissions_only_exposes_current_users_candidate_state(self):
        commission = self.commission()
        other = User.objects.create_user(username="other-artist")
        CommissionBid.objects.create(
            custom_request=commission,
            artist=other,
            amount=Decimal("123.45"),
            message="private other bid",
        )
        CommissionBid.objects.create(
            custom_request=commission,
            artist=self.artist,
            amount=Decimal("700.00"),
            message="my private bid",
        )
        CommissionInvitation.objects.create(
            custom_request=commission,
            artist=self.artist,
            invited_by=self.requester,
            amount=Decimal("750.00"),
            message="private invitation",
        )

        result = matching_open_commissions(self.artist)[0]

        self.assertEqual(result["bid_count"], 2)
        self.assertEqual(result["my_bid_status"], CommissionBid.Status.ACTIVE)
        self.assertEqual(
            result["my_invitation_status"], CommissionInvitation.Status.PENDING
        )
        serialized = str(result)
        self.assertNotIn("123.45", serialized)
        self.assertNotIn("700.00", serialized)
        self.assertNotIn("750.00", serialized)
        self.assertNotIn("private", serialized)

    def test_no_public_expertise_and_no_query_returns_no_claimed_match(self):
        novice = User.objects.create_user(username="novice", profile={"skills": "not-a-list"})
        self.commission()

        self.assertEqual(matching_open_commissions(novice), [])

    def test_owned_open_commission_is_strictly_scoped_and_uses_latest(self):
        older = self.commission(title="较早委托")
        latest = self.commission(title="最新委托")
        stranger = User.objects.create_user(username="stranger")
        strangers_commission = self.commission(requester=stranger, title="他人的委托")
        closed = self.commission(title="已关闭", status=CustomRequest.Status.CANCELLED)

        self.assertEqual(owned_open_commission(self.requester)["id"], latest.id)
        self.assertEqual(
            owned_open_commission(self.requester, older.id)["id"], older.id
        )
        self.assertIsNone(owned_open_commission(self.requester, strangers_commission.id))
        self.assertIsNone(owned_open_commission(self.requester, closed.id))
        self.assertIsNone(owned_open_commission(self.requester, "invalid"))

    def test_artist_matching_requires_active_artist_with_available_matching_work(self):
        commission = self.commission()
        matching_artist = User.objects.create_user(
            username="guofeng-pro",
            email="secret@example.test",
            bio="擅长国风角色",
            profile={"displayName": "国风老师", "skills": ["古风头像"]},
        )
        Artwork.objects.create(
            owner=matching_artist,
            title="水墨头像",
            category="古风",
            tags=["水墨"],
            price=100,
            is_available=True,
        )
        unrelated = User.objects.create_user(
            username="building-artist", profile={"skills": ["建筑"]}
        )
        Artwork.objects.create(
            owner=unrelated,
            title="摩天楼",
            category="建筑",
            tags=["写实"],
            price=100,
            is_available=True,
        )
        inactive = User.objects.create_user(
            username="inactive-artist", is_active=False, profile={"skills": ["古风"]}
        )
        Artwork.objects.create(
            owner=inactive,
            title="古风图",
            category="古风",
            tags=["水墨"],
            price=100,
            is_available=True,
        )
        unavailable = User.objects.create_user(
            username="unavailable-artist", profile={"skills": ["古风"]}
        )
        Artwork.objects.create(
            owner=unavailable,
            title="旧古风图",
            category="古风",
            tags=["水墨"],
            price=100,
            is_available=False,
        )

        result = matching_artists_for_owned_commission(
            self.requester, commission_id=commission.id
        )

        ids = [item["id"] for item in result["artists"]]
        self.assertIn(matching_artist.id, ids)
        # The requester also has no candidate entry even if they publish work later.
        self.assertNotIn(self.requester.id, ids)
        self.assertNotIn(unrelated.id, ids)
        self.assertNotIn(inactive.id, ids)
        self.assertNotIn(unavailable.id, ids)
        candidate = next(item for item in result["artists"] if item["id"] == matching_artist.id)
        self.assertEqual(
            set(candidate),
            {
                "id",
                "username",
                "display_name",
                "bio",
                "skills",
                "categories",
                "tags",
                "available_work_count",
                "reviews_count",
                "match_score",
            },
        )
        self.assertNotIn("email", candidate)

    def test_artist_matching_never_resolves_another_users_or_closed_commission(self):
        own = self.commission()
        stranger = User.objects.create_user(username="other-requester")
        foreign = self.commission(requester=stranger)
        closed = self.commission(status=CustomRequest.Status.COMPLETED)

        self.assertIsNotNone(
            matching_artists_for_owned_commission(
                self.requester, commission_id=own.id
            )["commission"]
        )
        self.assertEqual(
            matching_artists_for_owned_commission(
                self.requester, commission_id=foreign.id
            ),
            {"commission": None, "artists": []},
        )
        self.assertEqual(
            matching_artists_for_owned_commission(
                self.requester, commission_id=closed.id
            ),
            {"commission": None, "artists": []},
        )

    def test_explicit_reference_parser_does_not_treat_budget_as_an_id(self):
        self.assertEqual(extract_commission_reference("看看[委托:12]"), 12)
        self.assertEqual(extract_commission_reference("帮我看第 9 号委托"), 9)
        self.assertEqual(extract_commission_reference("看看 8 号委托"), 8)
        self.assertEqual(extract_commission_reference("委托 #7号适合谁"), 7)
        self.assertEqual(extract_commission_reference("委托 #6 适合谁"), 6)
        self.assertIsNone(extract_commission_reference("找预算 800 元的委托"))
