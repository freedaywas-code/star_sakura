import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


INTENT_GREETING = "greeting"
INTENT_CAPABILITIES = "capabilities"
INTENT_COMMISSION = "commission"
INTENT_DIRECT_MESSAGE = "direct_message"
INTENT_CONVERSATION = "conversation"
INTENT_ARTWORK_SEARCH = "artwork_search"
INTENT_ARTIST_SEARCH = "artist_search"
INTENT_PRICE_BUDGET = "price_budget"
INTENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentResult:
    name: str
    query_terms: tuple[str, ...] = ()
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    ordinal: int | None = None

    @property
    def has_text_conditions(self):
        return bool(self.query_terms)

    @property
    def has_budget(self):
        return self.min_price is not None or self.max_price is not None


_NUMBER = r"(?:\d+(?:\.\d{1,2})?)"
_ORDINALS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _extract_budget(message):
    text = message.lower().replace(",", "")
    range_match = re.search(
        rf"[¥￥]?\s*({_NUMBER})\s*(?:元)?\s*(?:-|—|~|～|至|到)\s*[¥￥]?\s*({_NUMBER})",
        text,
    )
    if range_match:
        first = _decimal(range_match.group(1))
        second = _decimal(range_match.group(2))
        if first is not None and second is not None:
            return min(first, second), max(first, second)

    maximum_patterns = (
        rf"(?:不超过|不高于|低于|少于|最多|上限)\s*[¥￥]?\s*({_NUMBER})",
        rf"[¥￥]?\s*({_NUMBER})\s*(?:元)?\s*(?:以内|以下|之内|封顶)",
        rf"(?:预算|价位|价格)\s*(?:是|为|大概|约|在)?\s*[¥￥]?\s*({_NUMBER})",
        rf"[¥￥]?\s*({_NUMBER})\s*元?\s*左右",
    )
    for pattern in maximum_patterns:
        match = re.search(pattern, text)
        if match:
            return None, _decimal(match.group(1))

    minimum_patterns = (
        rf"(?:不少于|不低于|高于|超过|至少)\s*[¥￥]?\s*({_NUMBER})",
        rf"[¥￥]?\s*({_NUMBER})\s*(?:元)?\s*(?:以上|起)",
    )
    for pattern in minimum_patterns:
        match = re.search(pattern, text)
        if match:
            return _decimal(match.group(1)), None
    return None, None


def _extract_ordinal(message):
    if not re.search(r"多少钱|价格|价钱|报价", message):
        return None
    match = re.search(r"第?\s*(\d+|[一二两三四五六七八九十])\s*个", message)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        number = int(value)
        return number if 1 <= number <= 20 else None
    return _ORDINALS.get(value)


_QUERY_NOISE = (
    "帮我",
    "给我",
    "请问",
    "麻烦",
    "我想要",
    "我想看",
    "想看",
    "找一下",
    "找一些",
    "找",
    "搜索一下",
    "搜索",
    "搜一下",
    "搜",
    "推荐一下",
    "推荐一些",
    "推荐几个",
    "推荐",
    "看看",
    "来点",
    "作品",
    "画作",
    "插画",
    "图片",
    "画师",
    "画家",
    "作者",
    "作家",
    "价格",
    "价位",
    "预算",
    "便宜的",
    "在售",
    "可购买",
    "一个",
    "一些",
    "几个",
    "有没有",
    "有吗",
    "的",
)


def _query_terms(message):
    text = message.lower()
    text = re.sub(rf"[¥￥]?\s*{_NUMBER}\s*(?:元)?", " ", text)
    text = re.sub(r"(?:以内|以下|以上|之内|封顶|左右|不超过|不高于|不低于|低于|高于|至少|最多)", " ", text)
    for noise in _QUERY_NOISE:
        text = text.replace(noise, " ")
    pieces = re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", text)
    result = []
    for piece in pieces:
        value = piece.strip("-_ ")
        is_single_chinese_condition = bool(re.fullmatch(r"[\u4e00-\u9fff]", value))
        if (len(value) < 2 and not is_single_chinese_condition) or value in {
            "我",
            "想",
            "要",
            "看",
            "想要",
            "需要",
            "可以",
            "适合",
            "比较",
            "一点",
        }:
            continue
        if value not in result:
            result.append(value[:50])
    return tuple(result[:12])


def classify_message(message):
    text = (message or "").strip()
    compact = re.sub(r"[\s，。！？!?、~～]+", "", text.lower())
    min_price, max_price = _extract_budget(text)
    ordinal = _extract_ordinal(text)

    if ordinal is not None:
        return IntentResult(
            INTENT_PRICE_BUDGET,
            min_price=min_price,
            max_price=max_price,
            ordinal=ordinal,
        )

    greeting_phrases = {"你好", "您好", "嗨", "哈喽", "hello", "hi", "早上好", "下午好", "晚上好", "在吗"}
    greeting_match = re.match(
        r"^(?:你好|您好|嗨|哈喽|hello|hi)(?=$|[\s，。！？!?、~～啊呀哇哦啦喽])",
        text.lower(),
    )
    greeting_remainder = ""
    if greeting_match:
        greeting_remainder = text[greeting_match.end() :].strip(
            " \t\r\n，。！？!?、~～啊呀哇哦啦喽"
        )

    # Topic changes and ordinary self-disclosure are conversation, even when
    # they happen to contain platform terms such as “粉丝”. This guard must run
    # before feature intents so “我是绝区零的粉丝” is not treated as a request
    # about the site's follower/private-message feature.
    is_topic_change = any(
        phrase in compact
        for phrase in (
            "不聊这些",
            "别聊这些",
            "不想聊这些",
            "换个话题",
            "换一个话题",
            "聊点别的",
            "聊些别的",
            "别再推荐",
            "不要再推荐",
            "不想看作品",
            "不聊委托",
            "别聊委托",
            "不想聊委托",
        )
    )
    is_chat_request = any(
        phrase in compact
        for phrase in (
            "陪我聊天",
            "陪我聊聊",
            "聊聊天",
            "随便聊聊",
            "找个人聊天",
            "找人聊天",
            "想和你聊天",
            "想找你聊天",
        )
    )
    is_self_disclosure = bool(
        re.search(
            r"(?:我是(?:一个)?|我也是|作为(?:一个)?).{1,40}?(?:的)?(?:粉丝|玩家|爱好者|观众|读者)(?:$|[，。！？!?])",
            text,
        )
    )
    if is_topic_change:
        return IntentResult(INTENT_CONVERSATION)

    commission_terms = ("委托", "约稿", "竞价", "报价", "接单")
    invitation_context_terms = ("画师", "画家", "作家", "作画", "接稿", "定向")
    if any(keyword in compact for keyword in commission_terms) or (
        "邀请" in compact
        and any(keyword in compact for keyword in invitation_context_terms)
    ):
        return IntentResult(INTENT_COMMISSION)

    strong_message_terms = ("私信", "私聊", "互关", "发消息")
    social_terms = ("关注", "粉丝")
    platform_social_phrases = (
        "个人主页",
        "粉丝列表",
        "关注列表",
        "我的粉丝",
        "我的关注",
        "查看粉丝",
        "查看关注",
        "谁关注我",
        "关注我的人",
        "我关注的人",
        "关注的人在哪",
        "取消关注",
        "粉丝数量",
        "关注数量",
        "粉丝在哪",
        "粉丝有多少",
    )
    if any(keyword in compact for keyword in strong_message_terms) or (
        any(keyword in compact for keyword in social_terms)
        and any(phrase in compact for phrase in platform_social_phrases)
    ):
        return IntentResult(INTENT_DIRECT_MESSAGE)

    capability_phrases = (
        "你能做什么",
        "你会什么",
        "有什么功能",
        "怎么使用",
        "如何使用",
        "使用帮助",
        "你的能力",
        "你有什么能力",
        "你能帮我什么",
        "你可以帮我什么",
    )
    if any(phrase in compact for phrase in capability_phrases) or compact in {
        "能力",
        "功能",
        "帮助",
    }:
        return IntentResult(INTENT_CAPABILITIES)

    is_search_request = any(
        keyword in compact for keyword in ("推荐", "搜索", "搜", "想看", "看看")
    ) or ("找" in compact and "找不到" not in compact)
    if not is_search_request and any(
        keyword in compact for keyword in ("多少钱", "价格", "价钱", "价位", "预算")
    ):
        return IntentResult(
            INTENT_PRICE_BUDGET,
            query_terms=_query_terms(text),
            min_price=min_price,
            max_price=max_price,
        )

    if any(keyword in compact for keyword in ("画师", "画家", "作者", "作家")):
        return IntentResult(
            INTENT_ARTIST_SEARCH,
            query_terms=_query_terms(text),
            min_price=min_price,
            max_price=max_price,
        )

    has_artwork_term = any(
        keyword in compact for keyword in ("作品", "画作", "插画", "图片")
    )
    non_artwork_search_terms = (
        "电影",
        "电视剧",
        "剧集",
        "动画",
        "动漫",
        "游戏",
        "音乐",
        "歌曲",
        "小说",
        "书籍",
        "一本书",
        "图书",
        "工作",
        "职位",
        "餐厅",
        "饭店",
        "旅游",
        "景点",
        "聊天",
        "天气",
    )
    is_non_artwork_search = is_search_request and any(
        keyword in compact for keyword in non_artwork_search_terms
    )
    if has_artwork_term or (is_search_request and not is_non_artwork_search):
        return IntentResult(
            INTENT_ARTWORK_SEARCH,
            query_terms=_query_terms(text),
            min_price=min_price,
            max_price=max_price,
        )

    if min_price is not None or max_price is not None or any(
        keyword in compact for keyword in ("价格", "价位", "预算", "多少钱", "便宜")
    ):
        return IntentResult(
            INTENT_PRICE_BUDGET,
            query_terms=_query_terms(text),
            min_price=min_price,
            max_price=max_price,
        )

    if compact in greeting_phrases or (
        greeting_match and (not greeting_remainder or is_chat_request)
    ):
        return IntentResult(INTENT_GREETING)

    if is_chat_request or is_self_disclosure or is_non_artwork_search:
        return IntentResult(INTENT_CONVERSATION)

    return IntentResult(INTENT_UNKNOWN)
