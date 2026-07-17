import http.client
import json
import socket
import threading
import time
import traceback
import uuid
from urllib.error import URLError
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork
from apps.users.models import User

from .ai import (
    AIConfig,
    AIServiceError,
    _Bulkhead,
    _PinnedHTTPSConnection,
    _open_connection,
    _request,
    call_ai,
    get_ai_config,
    stream_ai,
    validate_custom_api_base,
)
from .models import AIChatMessage, UserAISettings


class _JSONResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit=-1):
        return self.payload


class _StreamResponse:
    def __init__(self, lines):
        self.lines = iter(lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def readline(self, _limit=-1):
        try:
            value = next(self.lines)
        except StopIteration:
            return b""
        if isinstance(value, Exception):
            raise value
        return value


class _Read1Response:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read1(self, _limit=-1):
        return next(self.chunks, b"")


class _CaptureSocket:
    def __init__(self):
        self.sent = bytearray()

    def sendall(self, data):
        self.sent.extend(data)

    def settimeout(self, _timeout):
        pass

    def close(self):
        pass


class AIUpstreamDeadlineTests(SimpleTestCase):
    def config(self):
        return AIConfig(
            api_key="deadline-test-key",
            endpoint="https://provider.example/v1/chat/completions",
            model="deadline-model",
            provider="official",
            timeout=1,
            max_output_length=12000,
        )

    @patch("apps.recommendations.ai.time.monotonic")
    @patch("apps.recommendations.ai._open_connection")
    def test_non_stream_slow_drip_exceeds_total_deadline(self, mocked_open, clock):
        mocked_open.return_value = _Read1Response([b'{"choices":'])
        clock.side_effect = [0.0, 0.1, 0.2, 1.1]

        with self.assertRaises(AIServiceError):
            call_ai("system", [], config=self.config())

    @patch("apps.recommendations.ai.time.monotonic")
    @patch("apps.recommendations.ai._open_connection")
    def test_stream_slow_drip_exceeds_total_deadline(self, mocked_open, clock):
        mocked_open.return_value = _Read1Response(
            [b'data: {"choices":[{"delta":{"content":"partial"}}]}\n']
        )
        clock.side_effect = [0.0, 0.1, 1.1]

        with self.assertRaises(AIServiceError):
            list(stream_ai("system", [], config=self.config()))

    @patch("apps.recommendations.ai._open_connection")
    def test_stream_consumes_every_line_from_one_chunk(self, mocked_open):
        mocked_open.return_value = _Read1Response(
            [
                (
                    'data: {"choices":[{"delta":{"content":"甲"}}]}\n'
                    'data: {"choices":[{"delta":{"content":"乙"}}]}\n'
                    "data: [DONE]\n"
                ).encode("utf-8")
            ]
        )

        self.assertEqual(
            list(stream_ai("system", [], config=self.config())),
            ["甲", "乙"],
        )

    @patch("apps.recommendations.ai._open_connection")
    def test_many_empty_sse_events_are_consumed_without_buffer_growth(self, mocked_open):
        mocked_open.return_value = _Read1Response(
            [(b"data:\n" * 5000) + b"data: [DONE]\n"]
        )

        self.assertEqual(list(stream_ai("system", [], config=self.config())), [])

    @patch("apps.recommendations.ai._open_connection")
    def test_stream_raw_byte_limit_is_enforced(self, mocked_open):
        mocked_open.return_value = _Read1Response([b"x" * 96001])

        with self.assertRaises(AIServiceError):
            list(stream_ai("system", [], config=self.config()))

    @patch("apps.recommendations.ai._open_connection")
    def test_slow_headers_have_a_hard_wait_timeout(self, mocked_open):
        config = self.config()
        object.__setattr__(config, "timeout", 0.05)

        def slow_headers(*_args):
            time.sleep(0.2)
            return _JSONResponse({"choices": [{"message": {"content": "late"}}]})

        mocked_open.side_effect = slow_headers
        started = time.perf_counter()
        with self.assertRaises(AIServiceError):
            call_ai("system", [], config=config)
        self.assertLess(time.perf_counter() - started, 0.15)

    @override_settings(AI_DNS_TIMEOUT=0.05)
    @patch("apps.recommendations.ai.socket.getaddrinfo")
    def test_slow_dns_has_a_hard_wait_timeout(self, resolver):
        def slow_dns(*_args, **_kwargs):
            time.sleep(0.2)
            return [(2, 1, 6, "", ("93.184.216.34", 443))]

        resolver.side_effect = slow_dns
        started = time.perf_counter()
        with self.assertRaises(AIServiceError):
            validate_custom_api_base("https://provider.example/v1")
        self.assertLess(time.perf_counter() - started, 0.15)

    def test_bulkhead_has_no_queue_and_releases_only_after_completion(self):
        bulkhead = _Bulkhead(1, "test-bulkhead")
        started = threading.Event()
        release = threading.Event()
        result = []

        def blocking():
            started.set()
            release.wait(1)
            return "finished"

        thread = threading.Thread(
            target=lambda: result.append(
                bulkhead.run(
                    blocking,
                    1,
                    busy_message="busy",
                    timeout_message="timeout",
                )
            )
        )
        thread.start()
        self.assertTrue(started.wait(0.2))
        with self.assertRaises(AIServiceError):
            bulkhead.run(
                lambda: "queued",
                0.1,
                busy_message="busy",
                timeout_message="timeout",
            )
        release.set()
        thread.join(1)
        self.assertEqual(result, ["finished"])
        self.assertEqual(
            bulkhead.run(
                lambda: "next",
                0.1,
                busy_message="busy",
                timeout_message="timeout",
            ),
            "next",
        )

    @patch("apps.recommendations.ai._open_connection")
    def test_http_protocol_errors_are_safely_wrapped(self, mocked_open):
        mocked_open.side_effect = http.client.BadStatusLine("secret-key-not-a-status")
        with self.assertRaises(AIServiceError) as raised:
            call_ai("system", [], config=self.config())
        self.assertNotIn("secret-key-not-a-status", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        rendered = "".join(
            traceback.format_exception(
                type(raised.exception),
                raised.exception,
                raised.exception.__traceback__,
            )
        )
        self.assertNotIn("secret-key-not-a-status", rendered)

    def test_legacy_unsafe_keys_are_rejected_before_header_construction(self):
        unsafe_keys = (
            "dummy-marker\r\nInjected: value",
            "dummy marker",
            "dummy-密钥",
            "dummy\x7fmarker",
        )
        for api_key in unsafe_keys:
            with self.subTest(api_key=repr(api_key)):
                config = AIConfig(
                    api_key=api_key,
                    endpoint="https://provider.example/chat/completions",
                    model="model",
                    provider="official",
                    timeout=1,
                    max_output_length=256,
                )
                with self.assertRaises(AIServiceError) as raised:
                    _request(config, "system", [], stream=False)
                self.assertNotIn("dummy", str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)

    @patch("apps.recommendations.ai._open_connection")
    def test_residual_header_value_error_is_sanitized(self, mocked_open):
        mocked_open.side_effect = ValueError("Bearer dummy-marker-secret")

        with self.assertRaises(AIServiceError) as raised:
            call_ai("system", [], config=self.config())

        self.assertNotIn("dummy-marker-secret", str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    @patch("apps.recommendations.ai._open_connection")
    def test_malformed_provider_body_has_no_sensitive_exception_chain(self, mocked_open):
        mocked_open.return_value = _Read1Response(
            [b"Bearer dummy-malformed-marker is not JSON"]
        )

        with self.assertRaises(AIServiceError) as raised:
            call_ai("system", [], config=self.config())

        self.assertIsNone(raised.exception.__cause__)
        rendered = "".join(
            traceback.format_exception(
                type(raised.exception),
                raised.exception,
                raised.exception.__traceback__,
            )
        )
        self.assertNotIn("dummy-malformed-marker", rendered)

    @patch("apps.recommendations.ai._open_connection")
    def test_provider_cannot_echo_api_key_into_non_stream_content(self, mocked_open):
        config = self.config()
        mocked_open.return_value = _JSONResponse(
            {
                "choices": [
                    {"message": {"content": f"echo {config.api_key}"}}
                ]
            }
        )

        with self.assertRaises(AIServiceError) as raised:
            call_ai("system", [], config=config)

        self.assertNotIn(config.api_key, str(raised.exception))

    @patch("apps.recommendations.ai._open_connection")
    def test_provider_cannot_echo_api_key_across_stream_chunks(self, mocked_open):
        config = self.config()
        first = config.api_key[:8]
        second = config.api_key[8:]
        mocked_open.return_value = _StreamResponse(
            [
                f'data: {{"choices":[{{"delta":{{"content":"{first}"}}}}]}}\n'.encode(),
                f'data: {{"choices":[{{"delta":{{"content":"{second}"}}}}]}}\n'.encode(),
                b"data: [DONE]\n",
            ]
        )

        with self.assertRaises(AIServiceError) as raised:
            list(stream_ai("system", [], config=config))

        self.assertNotIn(config.api_key, str(raised.exception))

    def test_config_repr_hides_credentials_and_resolved_addresses(self):
        config = AIConfig(
            api_key="repr-secret-key",
            endpoint="https://provider.example/chat/completions",
            model="model",
            provider="custom",
            timeout=1,
            max_output_length=256,
            resolved_addresses=(
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, ("93.184.216.34", 443)),
            ),
        )
        rendered = repr(config)
        self.assertNotIn("repr-secret-key", rendered)
        self.assertNotIn("93.184.216.34", rendered)


class PinnedHTTPSTransportTests(SimpleTestCase):
    RECORD = (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        ("93.184.216.34", 443),
    )

    @patch("apps.recommendations.ai.socket.getaddrinfo")
    @patch("apps.recommendations.ai.socket.socket")
    def test_connect_uses_pinned_ip_but_original_hostname_for_sni(
        self,
        socket_factory,
        resolver,
    ):
        raw_socket = socket_factory.return_value
        connection = _PinnedHTTPSConnection(
            "provider.example",
            443,
            self.RECORD,
            timeout=1,
        )
        connection._context = MagicMock()

        connection.connect()

        raw_socket.connect.assert_called_once_with(("93.184.216.34", 443))
        connection._context.wrap_socket.assert_called_once_with(
            raw_socket,
            server_hostname="provider.example",
        )
        resolver.assert_not_called()

    def test_http_host_header_uses_original_hostname(self):
        connection = _PinnedHTTPSConnection(
            "provider.example",
            443,
            self.RECORD,
            timeout=1,
        )
        capture = _CaptureSocket()
        connection.sock = capture

        connection.request("POST", "/v1/chat/completions", body=b"{}")

        request_bytes = bytes(capture.sent)
        self.assertIn(b"Host: provider.example\r\n", request_bytes)
        self.assertNotIn(b"Host: 93.184.216.34", request_bytes)


class AIChatAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="reader",
            password="safe-test-password",
            profile={"homeTags": ["古风", "水墨"]},
        )
        self.artist = User.objects.create_user(
            username="artist",
            password="safe-test-password",
            bio="擅长古风插画",
        )
        self.artwork = Artwork.objects.create(
            owner=self.artist,
            title="山河入梦",
            description="水墨山水",
            category="古风",
            tags=["水墨", "山水"],
            price="88.00",
        )
        self.client.force_authenticate(self.user)

    @override_settings(AI_API_KEY="")
    @patch("apps.recommendations.ai.urlopen")
    def test_missing_key_uses_real_artwork_locally_without_network(self, mocked_urlopen):
        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐一些古风作品", "conversation_id": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["mode"], "local")
        self.assertIn("山河入梦", data["content"])
        self.assertIn(f"[作品:{self.artwork.id}]", data["content"])
        self.assertEqual(data["artworks"][0]["title"], "山河入梦")
        self.assertNotIn("localhost", json.dumps(data, ensure_ascii=False))
        self.assertEqual(AIChatMessage.objects.filter(user=self.user).count(), 2)
        self.assertEqual(
            AIChatMessage.objects.get(user=self.user, is_user=False).response_mode,
            "local",
        )
        mocked_urlopen.assert_not_called()

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_openai_compatible_request_and_structured_artworks(self, mocked_urlopen):
        mocked_urlopen.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "推荐《山河入梦》[作品:1]"}}]}
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "我想看水墨"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "ai")
        self.assertEqual(response.data["data"]["artworks"][0]["id"], self.artwork.id)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://open.bigmodel.cn/api/paas/v4/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-provider-key")
        self.assertEqual(payload["model"], "glm-4-flash")
        self.assertNotIn("temperature", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertIn("山河入梦", payload["messages"][0]["content"])
        assistant = AIChatMessage.objects.get(is_user=False)
        self.assertNotIn("test-provider-key", assistant.message)
        self.assertEqual(assistant.response_mode, "ai")

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="http://127.0.0.1:9000/v1",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_local_or_insecure_provider_url_is_rejected_and_falls_back(self, mocked_urlopen):
        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐作品"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "local")
        mocked_urlopen.assert_not_called()

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_stream_saves_only_complete_assistant_message(self, mocked_urlopen):
        mocked_urlopen.return_value = _StreamResponse(
            [
                'data: {"choices":[{"delta":{"content":"真实"}}]}\n'.encode(),
                'data: {"choices":[{"delta":{"content":"回复"}}]}\n'.encode(),
                b"data: [DONE]\n",
            ]
        )
        response = self.client.post(
            "/api/recommend/chat/stream/",
            {"content": "推荐古风"},
            format="json",
        )
        stream_body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"done": true', stream_body)
        self.assertIn('"mode": "ai"', stream_body)
        assistant = AIChatMessage.objects.get(user=self.user, is_user=False)
        self.assertEqual(assistant.message, "真实回复")

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_interrupted_stream_saves_a_validated_fallback_message(self, mocked_urlopen):
        mocked_urlopen.return_value = _StreamResponse(
            [
                'data: {"choices":[{"delta":{"content":"半句"}}]}\n'.encode(),
                URLError("connection lost"),
            ]
        )
        response = self.client.post(
            "/api/recommend/chat/stream/",
            {"content": "推荐古风"},
            format="json",
        )
        stream_body = b"".join(response.streaming_content).decode("utf-8")

        self.assertIn('"mode": "fallback"', stream_body)
        assistant = AIChatMessage.objects.get(user=self.user, is_user=False)
        self.assertEqual(assistant.response_mode, "fallback")
        self.assertIn("山河入梦", assistant.message)
        self.assertEqual(AIChatMessage.objects.filter(user=self.user, is_user=True).count(), 1)

    @override_settings(AI_API_KEY="")
    def test_history_returns_latest_messages_in_chronological_order_and_is_private(self):
        conversation_id = uuid.uuid4()
        messages = [
            AIChatMessage.objects.create(
                user=self.user,
                conversation_id=conversation_id,
                message=f"消息 {index}",
                is_user=index % 2 == 0,
            )
            for index in range(5)
        ]
        other = User.objects.create_user(username="other", password="safe-test-password")
        AIChatMessage.objects.create(
            user=other,
            conversation_id=conversation_id,
            message="其他用户的秘密",
        )

        response = self.client.get(
            "/api/recommend/chat/history/",
            {"conversation_id": str(conversation_id), "limit": 2},
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["data"]["messages"]
        self.assertEqual([item["id"] for item in result], [messages[3].id, messages[4].id])
        self.assertIn("response_mode", result[0])
        self.assertNotIn("其他用户的秘密", json.dumps(result, ensure_ascii=False))

    @override_settings(AI_API_KEY="", AI_MAX_INPUT_LENGTH=10)
    def test_input_length_and_conversation_id_are_validated(self):
        too_long = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "超过十个字符的消息内容会被拒绝"},
            format="json",
        )
        invalid_id = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "短消息", "conversation_id": "not-a-uuid"},
            format="json",
        )

        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(invalid_id.status_code, 400)
        self.assertFalse(AIChatMessage.objects.exists())

    def test_clear_requires_conversation_id_and_does_not_delete_all_history(self):
        conversation_id = uuid.uuid4()
        message = AIChatMessage.objects.create(
            user=self.user,
            conversation_id=conversation_id,
            message="保留的消息",
        )

        missing_id = self.client.post(
            "/api/recommend/chat/clear/",
            {},
            format="json",
        )

        self.assertEqual(missing_id.status_code, 400)
        self.assertTrue(AIChatMessage.objects.filter(id=message.id).exists())

        cleared = self.client.post(
            "/api/recommend/chat/clear/",
            {"conversation_id": str(conversation_id)},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(AIChatMessage.objects.filter(id=message.id).exists())

    @override_settings(AI_API_KEY="")
    def test_non_artwork_local_intents_never_attach_artwork_cards(self):
        cases = (
            ("你好", "你好"),
            ("能力", "可以"),
            ("委托竞价功能怎么用，怎么邀请画师", "报价"),
            ("没有互关时私信功能有什么限制", "三条"),
            ("预算怎么设置", "预算"),
            ("这个作品多少钱", "作品卡片"),
            ("今天天气怎么样", "实时天气"),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                response = self.client.post(
                    "/api/recommend/chat/send/",
                    {"content": message},
                    format="json",
                )
                data = response.data["data"]
                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["mode"], "local")
                self.assertEqual(data["artworks"], [])
                self.assertIn(expected, data["content"])

    @override_settings(AI_API_KEY="")
    def test_local_chat_follows_daily_conversation_without_forcing_platform_topics(self):
        conversation_id = str(uuid.uuid4())
        cases = (
            ("你好，可以陪我聊天吗", "当然可以"),
            ("你好啊", "你好呀"),
            ("我们能不聊这些吗", "换个话题"),
            ("我是一个绝区零的粉丝", "《绝区零》"),
        )

        replies = []
        for message, expected in cases:
            response = self.client.post(
                "/api/recommend/chat/send/",
                {"content": message, "conversation_id": conversation_id},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            data = response.data["data"]
            self.assertEqual(data["mode"], "local")
            self.assertEqual(data["artworks"], [])
            self.assertIn(expected, data["content"])
            replies.append(data["content"])

        self.assertNotIn("我还不确定你想了解什么", "\n".join(replies))
        self.assertNotIn("个人主页可以查看自己的粉丝", replies[-1])
        self.assertNotIn("三条消息", replies[-1])

    @override_settings(AI_API_KEY="")
    def test_fan_word_only_uses_direct_message_intent_with_platform_context(self):
        casual = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "我关注绝区零很久了"},
            format="json",
        )
        platform = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "怎么查看自己的粉丝列表"},
            format="json",
        )

        self.assertEqual(casual.status_code, 200)
        self.assertNotIn("个人主页可以查看自己的粉丝", casual.data["data"]["content"])
        self.assertEqual(platform.status_code, 200)
        self.assertIn("个人主页可以查看自己的粉丝", platform.data["data"]["content"])

    @override_settings(AI_API_KEY="")
    def test_ordinary_phrases_do_not_collide_with_platform_keywords(self):
        cases = (
            ("别再推荐作品了，我们聊点别的", "换个话题", "没有找到"),
            ("我想找个人聊天", "当然可以", "站内真实作品"),
            ("朋友邀请我玩绝区零", "绝区零", "发布委托后"),
            ("我没有能力做好这件事", "没有能力", "我可以按标题"),
            ("绝区零粉丝怎么看新版本", "绝区零", "个人主页可以查看"),
            ("我关注的游戏怎么没更新", "游戏", "个人主页可以查看"),
            ("推荐一部电影", "电影", "站内真实作品"),
            ("推荐一本书", "一本书", "站内真实作品"),
            ("我找不到工作", "工作", "站内真实作品"),
        )

        for message, expected, forbidden in cases:
            with self.subTest(message=message):
                response = self.client.post(
                    "/api/recommend/chat/send/",
                    {"content": message},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                data = response.data["data"]
                self.assertEqual(data["mode"], "local")
                self.assertEqual(data["artworks"], [])
                self.assertIn(expected, data["content"])
                self.assertNotIn(forbidden, data["content"])

    @override_settings(AI_API_KEY="")
    def test_greeting_and_self_disclosure_do_not_hide_explicit_actions(self):
        cases = (
            ("你好，我想看水墨作品", "山河入梦"),
            ("你好，委托怎么竞价", "提交报价"),
            ("你好，我的粉丝列表在哪", "个人主页"),
            ("我关注的人在哪", "个人主页"),
            ("我是绝区零粉丝，帮我找同人作品", "没有找到"),
            ("我是画师A的粉丝，想私信他", "三条消息"),
        )

        for message, expected in cases:
            with self.subTest(message=message):
                response = self.client.post(
                    "/api/recommend/chat/send/",
                    {"content": message},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected, response.data["data"]["content"])

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_daily_conversation_still_uses_configured_model(self, mocked_urlopen):
        mocked_urlopen.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "当然可以，我们来聊绝区零。"}}]}
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "我是一个绝区零的粉丝"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "ai")
        self.assertEqual(response.data["data"]["content"], "当然可以，我们来聊绝区零。")
        mocked_urlopen.assert_called_once()

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_daily_conversation_uses_coherent_fallback_when_provider_fails(
        self, mocked_urlopen
    ):
        mocked_urlopen.side_effect = URLError("provider unavailable")

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "我是一个绝区零的粉丝"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["mode"], "fallback")
        self.assertIn("《绝区零》", data["content"])
        self.assertNotIn("个人主页可以查看自己的粉丝", data["content"])
        self.assertNotIn("三条消息", data["content"])

    @override_settings(AI_API_KEY="")
    def test_chinese_title_category_and_tag_are_direct_search_hits(self):
        for message in ("找山河入梦作品", "推荐古风作品", "我想看水墨画作"):
            with self.subTest(message=message):
                response = self.client.post(
                    "/api/recommend/chat/send/",
                    {"content": message},
                    format="json",
                )
                ids = [item["id"] for item in response.data["data"]["artworks"]]
                self.assertIn(self.artwork.id, ids)

    @override_settings(AI_API_KEY="")
    def test_explicit_unmatched_term_returns_no_zero_score_artworks(self):
        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐原神作品"},
            format="json",
        )

        data = response.data["data"]
        self.assertEqual(data["artworks"], [])
        self.assertNotIn("山河入梦", data["content"])
        self.assertIn("没有找到", data["content"])

        matching = Artwork.objects.create(
            owner=self.artist,
            title="提瓦特旅途",
            description="角色立绘",
            category="游戏同人",
            tags=["原神"],
            price="66.00",
        )
        matched = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐原神作品"},
            format="json",
        )
        self.assertEqual(
            [item["id"] for item in matched.data["data"]["artworks"]],
            [matching.id],
        )

    @override_settings(AI_API_KEY="")
    def test_budget_is_a_hard_database_filter(self):
        Artwork.objects.create(
            owner=self.artist,
            title="昂贵古风图",
            category="古风",
            tags=["古风"],
            price="188.00",
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "找100元以内的古风作品"},
            format="json",
        )

        works = response.data["data"]["artworks"]
        self.assertTrue(works)
        self.assertTrue(all(float(item["price"]) <= 100 for item in works))
        self.assertNotIn("昂贵古风图", response.data["data"]["content"])

    @override_settings(AI_API_KEY="")
    def test_artist_search_has_no_artwork_cards(self):
        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "找古风画家"},
            format="json",
        )

        data = response.data["data"]
        self.assertEqual(data["artworks"], [])
        self.assertIn("@artist", data["content"])

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_structured_artworks_only_include_ids_referenced_by_model(self, mocked_urlopen):
        second = Artwork.objects.create(
            owner=self.artist,
            title="月下小径",
            category="古风",
            tags=["月夜"],
            price="55.00",
        )
        mocked_urlopen.return_value = _JSONResponse(
            {
                "choices": [
                    {"message": {"content": f"只推荐《月下小径》[作品:{second.id}]"}}
                ]
            }
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐作品"},
            format="json",
        )

        self.assertEqual(response.data["data"]["mode"], "ai")
        self.assertEqual(
            [item["id"] for item in response.data["data"]["artworks"]],
            [second.id],
        )

    @override_settings(
        AI_API_KEY="test-provider-key",
        AI_API_BASE="https://open.bigmodel.cn/api/paas/v4",
        AI_MODEL="glm-4-flash",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_unknown_model_artwork_id_triggers_local_fallback(self, mocked_urlopen):
        mocked_urlopen.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "推荐虚构作品[作品:999999]"}}]}
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐古风作品"},
            format="json",
        )

        data = response.data["data"]
        self.assertEqual(data["mode"], "fallback")
        self.assertNotIn("999999", data["content"])
        self.assertEqual([item["id"] for item in data["artworks"]], [self.artwork.id])
        self.assertEqual(
            AIChatMessage.objects.get(is_user=False).response_mode,
            "fallback",
        )

    @override_settings(AI_API_KEY="")
    def test_second_artwork_price_followup_uses_previous_references(self):
        Artwork.objects.create(
            owner=self.artist,
            title="月下小径",
            category="古风",
            tags=["月夜"],
            price="55.00",
        )
        conversation_id = str(uuid.uuid4())
        first = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "推荐作品", "conversation_id": conversation_id},
            format="json",
        )
        second_work = first.data["data"]["artworks"][1]

        followup = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "第二个多少钱", "conversation_id": conversation_id},
            format="json",
        )

        data = followup.data["data"]
        self.assertEqual(data["mode"], "local")
        self.assertEqual(data["artworks"], [])
        self.assertIn(second_work["title"], data["content"])
        self.assertIn(second_work["price"], data["content"])

    @override_settings(AI_API_KEY="")
    def test_named_artwork_price_is_answered_from_database(self):
        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "山河入梦多少钱"},
            format="json",
        )

        data = response.data["data"]
        self.assertEqual(data["mode"], "local")
        self.assertIn("88.00", data["content"])
        self.assertEqual([item["id"] for item in data["artworks"]], [self.artwork.id])

    @override_settings(AI_API_KEY="", AI_MODEL="glm-4-flash")
    def test_conversations_expose_safe_assistant_status_and_history_mode(self):
        conversation_id = str(uuid.uuid4())
        self.client.post(
            "/api/recommend/chat/send/",
            {"content": "你好", "conversation_id": conversation_id},
            format="json",
        )

        conversations = self.client.get("/api/recommend/chat/conversations/")
        status = conversations.data["data"]["assistant_status"]
        self.assertEqual(
            status,
            {"configured": False, "mode": "local", "model": None},
        )
        self.assertNotIn("key", json.dumps(status).lower())

        history = self.client.get(
            "/api/recommend/chat/history/",
            {"conversation_id": conversation_id},
        )
        assistant = history.data["data"]["messages"][-1]
        self.assertEqual(assistant["response_mode"], "local")

    @override_settings(AI_API_KEY="test-provider-key", AI_MODEL="glm-4-flash")
    def test_configured_assistant_status_exposes_model_but_not_credentials(self):
        AIChatMessage.objects.create(
            user=self.user,
            message="已验证回复",
            is_user=False,
            response_mode="ai",
        )

        response = self.client.get("/api/recommend/chat/conversations/")
        status = response.data["data"]["assistant_status"]

        self.assertEqual(status["configured"], True)
        self.assertEqual(status["mode"], "ai")
        self.assertEqual(status["model"], "glm-4-flash")
        self.assertNotIn("test-provider-key", json.dumps(response.data))

    @override_settings(AI_API_KEY="", AI_MODEL="glm-4-flash")
    def test_status_does_not_claim_online_ai_after_key_is_removed(self):
        AIChatMessage.objects.create(
            user=self.user,
            message="旧的联网回复",
            is_user=False,
            response_mode="ai",
        )

        response = self.client.get("/api/recommend/chat/conversations/")

        self.assertEqual(
            response.data["data"]["assistant_status"],
            {"configured": False, "mode": "local", "model": None},
        )


class UserAISettingsAPITests(APITestCase):
    PUBLIC_DNS = [
        (2, 1, 6, "", ("93.184.216.34", 443)),
    ]

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="model-owner",
            password="safe-test-password",
        )
        self.other = User.objects.create_user(
            username="other-model-owner",
            password="safe-test-password",
        )
        self.client.force_authenticate(self.user)

    @override_settings(
        AI_API_KEY="official-test-key",
        AI_API_BASE="https://official.example/v1",
        AI_MODEL="official-model",
        AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret",
    )
    def test_get_exposes_availability_but_never_credentials(self):
        response = self.client.get("/api/recommend/settings/")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["mode"], "official")
        self.assertEqual(
            data["official"],
            {"available": True, "model": "official-model"},
        )
        self.assertEqual(
            data["custom"],
            {"api_base": "", "model": "", "has_api_key": False},
        )
        rendered = json.dumps(response.data)
        self.assertNotIn("official-test-key", rendered)
        self.assertNotIn("encrypted_api_key", rendered)

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://custom.example/v1",
    )
    def test_custom_key_is_encrypted_and_never_echoed(self, _validator):
        plaintext = "custom-secret-key-that-must-not-leak"
        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://custom.example/v1/",
                "model": "custom-model",
                "api_key": plaintext,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        saved = UserAISettings.objects.get(user=self.user)
        self.assertNotEqual(saved.encrypted_api_key, plaintext)
        self.assertNotIn(plaintext, saved.encrypted_api_key)
        self.assertEqual(saved.get_api_key(), plaintext)
        self.assertTrue(response.data["data"]["custom"]["has_api_key"])
        rendered = json.dumps(response.data)
        self.assertNotIn(plaintext, rendered)
        self.assertNotIn(saved.encrypted_api_key, rendered)

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://custom.example/v1",
    )
    def test_blank_key_preserves_existing_ciphertext(self, _validator):
        saved = UserAISettings(user=self.user, mode="custom")
        saved.custom_api_base = "https://custom.example/v1"
        saved.custom_model = "old-model"
        saved.set_api_key("preserved-key")
        saved.save()
        original_ciphertext = saved.encrypted_api_key

        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://custom.example/v1",
                "model": "new-model",
                "api_key": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.encrypted_api_key, original_ciphertext)
        self.assertEqual(saved.get_api_key(), "preserved-key")
        self.assertEqual(saved.custom_model, "new-model")

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://different.example/v1",
    )
    def test_cross_origin_change_requires_new_key_and_preserves_record(self, _validator):
        saved = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://custom.example/v1",
            custom_model="old-model",
        )
        saved.set_api_key("preserved-key")
        saved.save()
        original_ciphertext = saved.encrypted_api_key

        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://different.example/v1",
                "model": "new-model",
                "api_key": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        saved.refresh_from_db()
        self.assertEqual(saved.custom_api_base, "https://custom.example/v1")
        self.assertEqual(saved.custom_model, "old-model")
        self.assertEqual(saved.encrypted_api_key, original_ciphertext)
        self.assertEqual(saved.get_api_key(), "preserved-key")

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://custom.example/v2/chat",
    )
    def test_same_origin_path_change_can_preserve_key(self, _validator):
        saved = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://CUSTOM.example:443/v1",
            custom_model="old-model",
        )
        saved.set_api_key("preserved-key")
        saved.save()
        original_ciphertext = saved.encrypted_api_key

        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://custom.example/v2/chat",
                "model": "new-model",
                "api_key": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.custom_api_base, "https://custom.example/v2/chat")
        self.assertEqual(saved.custom_model, "new-model")
        self.assertEqual(saved.encrypted_api_key, original_ciphertext)
        self.assertEqual(saved.get_api_key(), "preserved-key")

    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://custom.example/v1",
    )
    def test_first_custom_configuration_requires_key(self, _validator):
        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://custom.example/v1",
                "model": "custom-model",
                "api_key": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    def test_custom_api_key_length_is_bounded(self):
        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://provider.example/v1",
                "model": "custom-model",
                "api_key": "k" * 4097,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://provider.example/v1",
    )
    def test_custom_api_key_must_be_printable_ascii(self, _validator):
        unsafe_keys = (
            "dummy-marker\r\nInjected: value",
            "dummy marker",
            "dummy-密钥",
            "dummy\x7fmarker",
        )
        for api_key in unsafe_keys:
            with self.subTest(api_key=repr(api_key)):
                response = self.client.put(
                    "/api/recommend/settings/",
                    {
                        "mode": "custom",
                        "api_base": "https://provider.example/v1",
                        "model": "custom-model",
                        "api_key": api_key,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                rendered = json.dumps(response.data, ensure_ascii=False)
                self.assertNotIn("dummy-marker", rendered)
                self.assertNotIn("dummy-密钥", rendered)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch("apps.recommendations.ai.socket.getaddrinfo")
    @patch("apps.recommendations.ai._open_connection")
    def test_legacy_encrypted_unsafe_key_never_reaches_http_headers(
        self,
        mocked_open,
        resolver,
    ):
        resolver.return_value = self.PUBLIC_DNS
        custom = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://provider.example/v1",
            custom_model="custom-model",
        )
        custom.set_api_key("legacy-dummy-marker\r\nInjected: value")
        custom.save()

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "你好"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "fallback")
        self.assertNotIn(
            "legacy-dummy-marker",
            json.dumps(response.data, ensure_ascii=False),
        )
        mocked_open.assert_not_called()

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch(
        "apps.recommendations.serializers.validate_custom_api_base",
        return_value="https://custom.example/v1",
    )
    def test_settings_are_isolated_by_user_and_delete_restores_official(self, _validator):
        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://custom.example/v1",
                "model": "private-model",
                "api_key": "private-key",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(self.other)
        other_view = self.client.get("/api/recommend/settings/")
        self.assertEqual(other_view.data["data"]["mode"], "official")
        self.assertEqual(other_view.data["data"]["custom"]["model"], "")

        self.client.force_authenticate(self.user)
        deleted = self.client.delete("/api/recommend/settings/")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.data["data"]["mode"], "official")
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    def test_ssrf_and_unsafe_url_forms_are_rejected(self):
        unsafe_urls = (
            "http://api.example.com/v1",
            "https://localhost/v1",
            "https://127.0.0.1/v1",
            "https://10.0.0.8/v1",
            "https://[::1]/v1",
            "https://[::ffff:127.0.0.1]/v1",
            "https://[2002:7f00:1::]/v1",
            "https://[64:ff9b::7f00:1]/v1",
            "https://[64:ff9b:1:7f00:1::]/v1",
            "https://[ff02::1]/v1",
            "https://224.0.0.1/v1",
            "https://240.0.0.1/v1",
            "https://0.0.0.0/v1",
            "https://user:pass@api.example.com/v1",
            "https://api.example.com/v1?target=x",
            "https://api.example.com/v1#fragment",
        )
        for api_base in unsafe_urls:
            with self.subTest(api_base=api_base):
                response = self.client.put(
                    "/api/recommend/settings/",
                    {
                        "mode": "custom",
                        "api_base": api_base,
                        "model": "custom-model",
                        "api_key": "custom-key",
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    @patch("apps.recommendations.ai.socket.getaddrinfo")
    def test_dns_names_resolving_to_private_addresses_are_rejected(self, resolver):
        resolver.return_value = [(2, 1, 6, "", ("192.168.1.7", 443))]
        response = self.client.put(
            "/api/recommend/settings/",
            {
                "mode": "custom",
                "api_base": "https://provider.example/v1",
                "model": "custom-model",
                "api_key": "custom-key",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    @patch("apps.recommendations.ai.socket.getaddrinfo")
    def test_dns_transition_and_special_addresses_are_rejected(self, resolver):
        unsafe_results = (
            "::ffff:127.0.0.1",
            "2002:7f00:1::",
            "64:ff9b::7f00:1",
            "64:ff9b:1:7f00:1::",
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",
            "ff02::1",
            "240.0.0.1",
        )
        for address in unsafe_results:
            with self.subTest(address=address):
                resolver.return_value = [(2, 1, 6, "", (address, 443))]
                response = self.client.put(
                    "/api/recommend/settings/",
                    {
                        "mode": "custom",
                        "api_base": "https://provider.example/v1",
                        "model": "custom-model",
                        "api_key": "custom-key",
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAISettings.objects.filter(user=self.user).exists())

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch("apps.recommendations.ai.socket.getaddrinfo")
    @patch("apps.recommendations.ai._PinnedHTTPSConnection")
    @patch("apps.recommendations.ai.urlopen")
    def test_custom_transport_reuses_resolved_ip_and_rejects_redirects(
        self,
        mocked_urlopen,
        connection_class,
        resolver,
    ):
        resolver.return_value = self.PUBLIC_DNS
        custom = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://custom.example/v1",
            custom_model="custom-model",
        )
        custom.set_api_key("custom-key")
        custom.save()
        config = get_ai_config(self.user)
        self.assertEqual(resolver.call_count, 1)
        redirect = MagicMock(status=302)
        connection_class.return_value.getresponse.return_value = redirect
        request = _request(
            config,
            "system",
            [{"role": "user", "content": "test"}],
            stream=False,
        )

        with self.assertRaises(AIServiceError):
            _open_connection(request, config)

        connection_class.assert_called_once_with(
            "custom.example",
            443,
            config.resolved_addresses[0],
            timeout=config.timeout,
        )
        self.assertEqual(resolver.call_count, 1)
        mocked_urlopen.assert_not_called()

    @override_settings(
        AI_API_KEY="official-key-must-not-be-used",
        AI_API_BASE="https://official.example/v1",
        AI_MODEL="official-model",
        AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret",
    )
    @patch("apps.recommendations.ai.socket.getaddrinfo")
    @patch("apps.recommendations.ai._open_connection")
    def test_chat_uses_each_users_selected_custom_provider(self, mocked_open, resolver):
        resolver.return_value = self.PUBLIC_DNS
        custom = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://custom.example/v1",
            custom_model="custom-model",
        )
        custom.set_api_key("custom-key")
        custom.save()
        mocked_open.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "你好，我是智能推荐助手。"}}]}
        )

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "你好"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "ai")
        request = mocked_open.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://custom.example/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer custom-key")
        self.assertEqual(payload["model"], "custom-model")
        self.assertNotIn("official-key-must-not-be-used", request.get_header("Authorization"))

    @override_settings(
        AI_API_KEY="official-key-must-not-be-used",
        AI_API_BASE="https://official.example/v1",
        AI_MODEL="official-model",
        AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_invalid_custom_config_uses_local_without_switching_to_official(self, mocked_urlopen):
        custom = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://127.0.0.1/v1",
            custom_model="custom-model",
        )
        custom.set_api_key("custom-key")
        custom.save()

        response = self.client.post(
            "/api/recommend/chat/send/",
            {"content": "你好"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["mode"], "local")
        mocked_urlopen.assert_not_called()

    @override_settings(AI_CREDENTIAL_ENCRYPTION_KEY="test-only-encryption-secret")
    @patch("apps.recommendations.ai.socket.getaddrinfo")
    @patch("apps.recommendations.ai._open_connection")
    def test_connection_test_calls_selected_model_and_returns_safe_status(
        self,
        mocked_open,
        resolver,
    ):
        resolver.return_value = self.PUBLIC_DNS
        custom = UserAISettings(
            user=self.user,
            mode="custom",
            custom_api_base="https://custom.example/v1",
            custom_model="custom-model",
        )
        custom.set_api_key("connection-secret")
        custom.save()
        mocked_open.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "OK"}}]}
        )

        response = self.client.post("/api/recommend/settings/test/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(
            response.data["data"],
            {"status": "success", "model": "custom-model", "provider": "custom"},
        )
        rendered = json.dumps(response.data)
        self.assertNotIn("connection-secret", rendered)
        request = mocked_open.call_args.args[0]
        self.assertFalse(json.loads(request.data.decode("utf-8"))["stream"])

    @override_settings(
        AI_API_KEY="official-test-key",
        AI_API_BASE="https://official.example/v1",
        AI_MODEL="official-model",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_connection_test_is_throttled(self, mocked_urlopen):
        mocked_urlopen.return_value = _JSONResponse(
            {"choices": [{"message": {"content": "OK"}}]}
        )

        responses = [
            self.client.post("/api/recommend/settings/test/", {}, format="json")
            for _ in range(6)
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)

    def test_settings_management_is_throttled(self):
        responses = [
            self.client.get("/api/recommend/settings/")
            for _ in range(31)
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:30]))
        self.assertEqual(responses[30].status_code, 429)

    @override_settings(
        AI_API_KEY="official-test-key",
        AI_API_BASE="https://official.example/v1",
        AI_MODEL="official-model",
    )
    @patch("apps.recommendations.ai.urlopen")
    def test_stream_failure_retries_non_stream_before_local_fallback(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            _StreamResponse([URLError("stream unsupported")]),
            _JSONResponse({"choices": [{"message": {"content": "非流式回复"}}]}),
        ]

        response = self.client.post(
            "/api/recommend/chat/stream/",
            {"content": "你好"},
            format="json",
        )
        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("非流式回复", body)
        self.assertIn('"mode": "ai"', body)
        requests = [call.args[0] for call in mocked_urlopen.call_args_list]
        self.assertTrue(json.loads(requests[0].data.decode("utf-8"))["stream"])
        self.assertFalse(json.loads(requests[1].data.decode("utf-8"))["stream"])
