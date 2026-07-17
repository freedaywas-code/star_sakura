from django.test import SimpleTestCase

from .local import (
    INTENT_ARTIST_SEARCH,
    INTENT_ARTWORK_SEARCH,
    INTENT_COMMISSION_ARTIST_MATCH,
    INTENT_COMMISSION_SEARCH,
    INTENT_DIRECT_MESSAGE,
    INTENT_PLATFORM_HELP,
    classify_message,
)


class PlatformIntentClassificationTests(SimpleTestCase):
    def assert_intent(self, message, expected):
        self.assertEqual(classify_message(message).name, expected, message)

    def test_explicit_platform_operation_questions_use_platform_help(self):
        for message in (
            "作品怎么评价",
            "报价可以修改吗",
            "成交价谁能看",
            "API Key怎么配置",
            "订单如何付款",
            "浏览历史在哪",
            "如何删除作品",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, INTENT_PLATFORM_HELP)

    def test_open_commission_search_stays_more_specific(self):
        for message in (
            "帮我找适合我接的古风委托",
            "推荐几个我能接的委托，可以吗",
            "搜索可以接的水墨委托",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, INTENT_COMMISSION_SEARCH)

    def test_search_how_to_is_platform_help_not_a_live_search(self):
        for message in (
            "怎么搜索委托",
            "委托搜索入口在哪里",
            "如何查看开放委托",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, INTENT_PLATFORM_HELP)

    def test_owned_commission_artist_matching_stays_more_specific(self):
        for message in (
            "给我的委托推荐合适的画师",
            "为我发布的约稿匹配画家",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, INTENT_COMMISSION_ARTIST_MATCH)

    def test_direct_message_questions_keep_direct_message_intent(self):
        for message in (
            "私信怎么发",
            "没互关可以发几条消息吗",
            "我的粉丝列表在哪里",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, INTENT_DIRECT_MESSAGE)

    def test_recommendations_and_non_questions_are_not_platform_help(self):
        cases = (
            ("推荐古风作品", INTENT_ARTWORK_SEARCH),
            ("可以推荐水墨画师吗", INTENT_ARTIST_SEARCH),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                self.assert_intent(message, expected)

        self.assertNotEqual(
            classify_message("我们聊聊作品评价吧").name,
            INTENT_PLATFORM_HELP,
        )
        self.assertNotEqual(
            classify_message("你怎么看这幅古风作品").name,
            INTENT_PLATFORM_HELP,
        )
        self.assert_intent("可以帮我搜索古风作品吗", INTENT_ARTWORK_SEARCH)
