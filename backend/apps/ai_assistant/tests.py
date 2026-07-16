import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork


class _Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(
    AI_API_KEY="platform-key",
    AI_API_BASE="https://example.ai/v1",
    AI_MODEL="test-model",
    AI_VISION_MODEL="test-vision-model",
)
class AIChatTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="creator", password="test-pass-123")
        self.artwork = Artwork.objects.create(
            owner=self.user, title="星空少女", category="原创", is_available=True
        )

    def test_login_is_required(self):
        response = self.client.post("/api/ai/chat/", {"message": "你好"}, format="json")
        self.assertEqual(response.status_code, 401)

    @patch("apps.ai_assistant.views.urlrequest.urlopen")
    def test_chat_uses_platform_defaults_and_returns_message(self, urlopen):
        urlopen.return_value = _Response(json.dumps({
            "model": "test-model",
            "choices": [{"message": {"content": "给你一个星空主题灵感。"}}],
        }).encode())
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/ai/chat/", {"message": "给我灵感"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["message"], "给你一个星空主题灵感。")
        sent_request = urlopen.call_args.args[0]
        self.assertEqual(sent_request.full_url, "https://example.ai/v1/chat/completions")
        self.assertEqual(sent_request.headers["Authorization"], "Bearer platform-key")

    @patch("apps.ai_assistant.views.urlrequest.urlopen")
    def test_custom_browser_config_overrides_defaults(self, urlopen):
        urlopen.return_value = _Response(b'{"choices":[{"message":{"content":"ok"}}]}')
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/ai/chat/", {
            "message": "hello",
            "api_key": "own-key",
            "api_base": "https://custom.example/v1",
            "model": "own-model",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        sent_request = urlopen.call_args.args[0]
        sent_body = json.loads(sent_request.data)
        self.assertEqual(sent_request.full_url, "https://custom.example/v1/chat/completions")
        self.assertEqual(sent_request.headers["Authorization"], "Bearer own-key")
        self.assertEqual(sent_body["model"], "own-model")

    @patch("apps.ai_assistant.views.urlrequest.urlopen")
    def test_recommendation_metadata_comes_from_database(self, urlopen):
        urlopen.return_value = _Response(json.dumps({
            "choices": [{"message": {"content": f"推荐《星空少女》【作品#{self.artwork.id}】"}}],
        }).encode())
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/ai/chat/", {"message": "推荐作品"}, format="json")

        preview = response.data["data"]["recommendations"][0]
        self.assertEqual(preview["type"], "artwork")
        self.assertEqual(preview["title"], "星空少女")
        self.assertIn("作者：creator", preview["subtitle"])

    @override_settings(AI_API_BASE="https://open.bigmodel.cn/api/paas/v4")
    @patch("apps.ai_assistant.views.urlrequest.urlopen")
    def test_art_question_enables_web_search_and_returns_sources(self, urlopen):
        urlopen.return_value = _Response(json.dumps({
            "choices": [{"message": {"content": "印象派重视瞬间光色。[来源: ref_1]"}}],
            "web_search": [{
                "title": "Impressionism",
                "link": "https://museum.example/impressionism",
                "media": "Example Museum",
                "publish_date": "2026-01-01",
                "content": "A museum introduction.",
                "refer": "ref_1",
            }],
        }).encode())
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/ai/chat/", {"message": "详细介绍印象派画风"}, format="json")

        sent_body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent_body["tools"][0]["type"], "web_search")
        self.assertTrue(response.data["data"]["web_search_used"])
        self.assertEqual(response.data["data"]["sources"][0]["title"], "Impressionism")

    @patch("apps.ai_assistant.views.urlrequest.urlopen")
    def test_uploaded_artwork_uses_vision_model_and_multimodal_content(self, urlopen):
        urlopen.return_value = _Response(b'{"choices":[{"message":{"content":"visual analysis"}}]}')
        self.client.force_authenticate(self.user)
        image_data = "data:image/png;base64," + ("a" * 32)

        response = self.client.post("/api/ai/chat/", {
            "message": "鉴赏这幅画",
            "image_data": image_data,
        }, format="json")

        self.assertEqual(response.status_code, 200)
        sent_body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent_body["model"], "test-vision-model")
        user_content = sent_body["messages"][-1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["image_url"]["url"], image_data)
