import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork
from apps.custom.models import CommissionBid, CommissionInvitation, CustomRequest
from apps.users.models import User


class _JSONResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit=-1):
        return self.payload


class AICommissionIntegrationTests(APITestCase):
    """End-to-end contract tests for commission matching in the unified chat API."""

    endpoint = "/api/recommend/chat/send/"

    def setUp(self):
        cache.clear()
        self.seeker = User.objects.create_user(
            username="ink-seeker",
            password="safe-test-password",
            email="seeker-private@example.test",
            profile={"skills": ["古风", "水墨"], "homeTags": ["国风"]},
        )
        Artwork.objects.create(
            owner=self.seeker,
            title="公开水墨样稿",
            description="公开作品描述",
            category="古风",
            tags=["水墨", "国风"],
            price=Decimal("88.00"),
        )

        self.requester = User.objects.create_user(
            username="commission-owner",
            password="safe-test-password",
            email="owner-private@example.test",
        )
        self.matching_commission = self._commission(
            title="古风水墨双人头像",
            type_label="古风头像",
            description="需要水墨质感与国风背景",
            budget=Decimal("800.00"),
        )
        self.too_cheap_commission = self._commission(
            title="低预算古风头像",
            type_label="古风头像",
            description="水墨风格",
            budget=Decimal("300.00"),
        )
        self.unrelated_commission = self._commission(
            title="现代办公楼建模",
            type_label="建筑",
            description="写实玻璃幕墙",
            budget=Decimal("1200.00"),
        )
        self._commission(
            title="已经接单的古风头像",
            type_label="古风头像",
            description="不应作为开放委托出现",
            budget=Decimal("900.00"),
            status=CustomRequest.Status.ACCEPTED,
            artist=self.seeker,
            agreed_price=Decimal("850.00"),
        )

        self.artist_candidate = User.objects.create_user(
            username="public-ink-artist",
            password="safe-test-password",
            email="artist-secret@example.test",
            bio="擅长古风和水墨头像",
            profile={
                "displayName": "水墨老师",
                "skills": ["古风头像", "水墨"],
                "privateNote": "PROFILE-PRIVATE-NOTE",
            },
        )
        Artwork.objects.create(
            owner=self.artist_candidate,
            title="水墨人物头像",
            description="公开样稿",
            category="古风头像",
            tags=["水墨", "国风"],
            price=Decimal("100.00"),
        )

        self.other_requester = User.objects.create_user(
            username="other-owner",
            password="safe-test-password",
            email="foreign-owner-secret@example.test",
        )
        self.foreign_commission = self._commission(
            requester=self.other_requester,
            title="FOREIGN-PRIVATE-TITLE",
            type_label="秘密类型",
            description="FOREIGN-PRIVATE-DESCRIPTION",
            budget=Decimal("999.00"),
        )

    def _commission(self, **overrides):
        values = {
            "requester": self.requester,
            "title": "默认委托",
            "type_label": "插画",
            "description": "默认说明",
            "budget": Decimal("500.00"),
            "budget_note": "可商议",
        }
        values.update(overrides)
        return CustomRequest.objects.create(**values)

    def _send(self, user, content):
        self.client.force_authenticate(user)
        return self.client.post(self.endpoint, {"content": content}, format="json")

    def assert_result_arrays(self, data):
        for field in ("artworks", "commissions", "artists"):
            self.assertIn(field, data)
            self.assertIsInstance(data[field], list)

    @override_settings(AI_API_KEY="")
    def test_searches_open_commissions_with_a_hard_budget_filter(self):
        response = self._send(
            self.seeker,
            "帮我找委托，古风，预算500元以上",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assert_result_arrays(data)
        self.assertEqual(data["artworks"], [])
        self.assertEqual(data["artists"], [])
        self.assertEqual(
            [item["id"] for item in data["commissions"]],
            [self.matching_commission.id],
        )
        self.assertTrue(
            all(Decimal(item["budget"]) >= Decimal("500") for item in data["commissions"])
        )
        self.assertIn(f"[委托:{self.matching_commission.id}]", data["content"])
        self.assertNotIn(str(self.too_cheap_commission.id), data["content"])
        self.assertNotIn(str(self.unrelated_commission.id), data["content"])
        serialized = json.dumps(data["commissions"], ensure_ascii=False)
        for forbidden_field in ("requester", "agreed_price", "selected_bid", "bids", "invitations"):
            self.assertNotIn(f'"{forbidden_field}"', serialized)

    @override_settings(AI_API_KEY="")
    def test_matches_public_artists_for_the_authenticated_users_open_commission(self):
        response = self._send(
            self.requester,
            f"请为我的[委托:{self.matching_commission.id}]推荐合适的画师",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assert_result_arrays(data)
        self.assertEqual(data["artworks"], [])
        self.assertIn(
            self.artist_candidate.id,
            [item["id"] for item in data["artists"]],
        )
        self.assertIn(f"[画师:{self.artist_candidate.id}]", data["content"])
        self.assertIn(self.matching_commission.title, data["content"])
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(self.artist_candidate.email, serialized)
        self.assertNotIn("PROFILE-PRIVATE-NOTE", serialized)
        self.assertNotIn('"profile"', serialized)

    @override_settings(AI_API_KEY="")
    def test_cannot_match_artists_for_another_users_commission(self):
        response = self._send(
            self.requester,
            f"请为我的[委托:{self.foreign_commission.id}]推荐合适的画师",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assert_result_arrays(data)
        self.assertEqual(data["artists"], [])
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(self.foreign_commission.title, serialized)
        self.assertNotIn(self.foreign_commission.description, serialized)
        self.assertNotIn(self.other_requester.email, serialized)

    @override_settings(AI_API_KEY="")
    def test_normal_chat_and_platform_help_keep_recommendation_arrays_empty(self):
        casual = self._send(self.seeker, "今天有点累，陪我聊聊天吧")
        help_response = self._send(self.seeker, "怎么发布作品")

        self.assertEqual(casual.status_code, 200)
        self.assertEqual(help_response.status_code, 200)
        for response in (casual, help_response):
            data = response.data["data"]
            self.assert_result_arrays(data)
            self.assertEqual(data["artworks"], [])
            self.assertEqual(data["commissions"], [])
            self.assertEqual(data["artists"], [])
        self.assertIn("发布", help_response.data["data"]["content"])
        self.assertIn("上传", help_response.data["data"]["content"])
        self.assertIn("名称", help_response.data["data"]["content"])

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_configured_model_returns_only_referenced_candidates_and_gets_no_private_bid_data(
        self, mocked_urlopen
    ):
        other_bidder = User.objects.create_user(
            username="other-bidder",
            email="bidder-private@example.test",
        )
        CommissionBid.objects.create(
            custom_request=self.matching_commission,
            artist=other_bidder,
            amount=Decimal("731.29"),
            message="OTHER-BID-PRIVATE-MESSAGE",
        )
        CommissionInvitation.objects.create(
            custom_request=self.matching_commission,
            artist=self.seeker,
            invited_by=self.requester,
            amount=Decimal("799.13"),
            message="INVITATION-PRIVATE-MESSAGE",
        )
        mocked_urlopen.return_value = _JSONResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                f"推荐《{self.matching_commission.title}》"
                                f"[委托:{self.matching_commission.id}]"
                            )
                        }
                    }
                ]
            }
        )

        response = self._send(self.seeker, "帮我找委托，古风")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["mode"], "ai")
        self.assert_result_arrays(data)
        self.assertEqual(
            [item["id"] for item in data["commissions"]],
            [self.matching_commission.id],
        )
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        prompt = payload["messages"][0]["content"]
        self.assertIn(self.matching_commission.title, prompt)
        for private_value in (
            "731.29",
            "799.13",
            "OTHER-BID-PRIVATE-MESSAGE",
            "INVITATION-PRIVATE-MESSAGE",
            other_bidder.email,
            self.seeker.email,
            self.requester.email,
        ):
            self.assertNotIn(private_value, prompt)
            self.assertNotIn(private_value, json.dumps(data, ensure_ascii=False))

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_configured_model_cannot_surface_a_commission_outside_candidates(
        self, mocked_urlopen
    ):
        fabricated_id = 999999
        mocked_urlopen.return_value = _JSONResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": f"推荐虚构委托[委托:{fabricated_id}]"
                        }
                    }
                ]
            }
        )

        response = self._send(self.seeker, "帮我找委托，古风")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["mode"], "fallback")
        self.assert_result_arrays(data)
        self.assertNotIn(f"[委托:{fabricated_id}]", data["content"])
        allowed = {self.matching_commission.id, self.too_cheap_commission.id}
        self.assertTrue({item["id"] for item in data["commissions"]}.issubset(allowed))
