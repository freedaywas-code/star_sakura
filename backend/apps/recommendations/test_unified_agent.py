import json
import uuid
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork
from apps.users.models import User

from .models import AIChatMessage
from .tests import _JSONResponse


class UnifiedChatRecommendationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="unified-reader",
            password="safe-test-password",
            profile={"homeTags": ["古风"]},
        )
        self.artist = User.objects.create_user(
            username="unified-artist",
            password="safe-test-password",
        )
        self.ancient_cheap = self.work("清风小像", "古风", "40.00")
        self.water_affordable = self.work("烟雨归舟", "水墨", "80.00")
        self.water_expensive = self.work("千山墨韵", "水墨", "120.00")
        self.zzz_artwork = self.work("新艾利都夜色", "游戏同人", "70.00", ["绝区零"])
        self.ancient_expensive = self.work("长安夜宴", "古风", "100.00")
        self.client.force_authenticate(self.user)

    def work(self, title, category, price, tags=None):
        return Artwork.objects.create(
            owner=self.artist,
            title=title,
            description=f"{category}作品",
            category=category,
            tags=tags or [category],
            price=price,
        )

    def send(self, content, conversation_id):
        return self.client.post(
            "/api/recommend/chat/send/",
            {"content": content, "conversation_id": str(conversation_id)},
            format="json",
        )

    @override_settings(AI_API_KEY="")
    def test_chat_topic_flows_into_related_artwork_request(self):
        conversation_id = uuid.uuid4()
        self.send("我是一个绝区零的粉丝", conversation_id)

        response = self.send("推荐一些相关作品", conversation_id)

        data = response.data["data"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in data["artworks"]], [self.zzz_artwork.id])

    @override_settings(AI_API_KEY="")
    def test_relative_price_and_style_followups_keep_context(self):
        first_id = uuid.uuid4()
        first = self.send("推荐古风作品", first_id).data["data"]
        cheaper = self.send("便宜一点", first_id).data["data"]
        self.assertTrue(cheaper["artworks"])
        self.assertLess(
            float(cheaper["artworks"][0]["price"]),
            float(first["artworks"][0]["price"]),
        )
        self.assertEqual(cheaper["artworks"][0]["category"], "古风")

        second_id = uuid.uuid4()
        self.send("找100元以内的古风作品", second_id)
        water = self.send("换成水墨的", second_id).data["data"]
        self.assertEqual([item["id"] for item in water["artworks"]], [self.water_affordable.id])
        self.assertNotIn(self.water_expensive.title, water["content"])

    @override_settings(AI_API_KEY="")
    def test_ordinal_survives_small_talk_but_not_another_conversation(self):
        conversation_id = uuid.uuid4()
        first = self.send("推荐作品", conversation_id).data["data"]
        expected = first["artworks"][1]
        self.send("谢谢你", conversation_id)

        price = self.send("第二个多少钱", conversation_id).data["data"]
        self.assertIn(expected["title"], price["content"])
        self.assertIn(expected["price"], price["content"])

        isolated = self.send("第二个多少钱", uuid.uuid4()).data["data"]["content"]
        self.assertIn("没有找到", isolated)
        self.assertNotIn(expected["title"], isolated)

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_configured_model_handles_recommendation_and_price_refinement(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            _JSONResponse({"choices": [{"message": {"content": f"《长安夜宴》[作品:{self.ancient_expensive.id}]"}}]}),
            _JSONResponse({"choices": [{"message": {"content": f"《清风小像》[作品:{self.ancient_cheap.id}]"}}]}),
        ]
        conversation_id = uuid.uuid4()

        first = self.send("推荐古风作品", conversation_id)
        cheaper = self.send("便宜一点", conversation_id)

        self.assertEqual(first.data["data"]["mode"], "ai")
        self.assertEqual(cheaper.data["data"]["mode"], "ai")
        self.assertEqual(mocked_urlopen.call_count, 2)
        payload = json.loads(mocked_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("最近推荐上下文", payload["messages"][0]["content"])
        turn = AIChatMessage.objects.filter(
            conversation_id=conversation_id,
            is_user=False,
        ).order_by("created_at", "id").first()
        self.assertEqual(turn.turn_data["shown_ids"], [self.ancient_expensive.id])
