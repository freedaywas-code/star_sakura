import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


INTENT_GREETING = "greeting"
INTENT_CAPABILITIES = "capabilities"
INTENT_COMMISSION = "commission"
INTENT_COMMISSION_SEARCH = "commission_search"
INTENT_COMMISSION_ARTIST_MATCH = "commission_artist_match"
INTENT_DIRECT_MESSAGE = "direct_message"
INTENT_PLATFORM_HELP = "platform_help"
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

    minimum_suffix_match = re.search(
        rf"[¥￥]?\s*({_NUMBER})\s*(?:元)?\s*(?:以上|起)",
        text,
    )
    if minimum_suffix_match:
        return _decimal(minimum_suffix_match.group(1)), None

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
    "相关的",
    "相关",
    "类似的",
    "类似",
    "这种",
    "这类",
    "同类",
    "的",
)


def extract_query_terms(message):
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


_COMMISSION_QUERY_NOISE = (
    "开放委托",
    "委托需求",
    "委托",
    "约稿需求",
    "约稿",
    "可以接的",
    "我能接的",
    "能接的",
    "适合我的",
    "符合我的",
    "适合我",
    "符合我",
    "接单",
    "单子",
    "订单",
    "查找",
    "查看",
)

_PLATFORM_HELP_PHRASES = (
    "怎么发布作品", "如何发布作品", "怎么上传作品", "如何上传作品",
    "怎么编辑作品", "如何编辑作品", "怎么删除作品", "如何删除作品",
    "怎么点赞", "如何点赞", "怎么收藏", "如何收藏",
    "浏览历史在哪", "怎么看浏览历史", "怎么注册", "如何注册",
    "怎么登录", "如何登录", "怎么修改密码", "如何修改密码", "怎么改密码",
    "怎么设置模型", "如何设置模型", "怎么配置api", "如何配置api",
    "api接口在哪", "模型设置在哪", "怎么切换模型", "如何切换模型",
    "怎么搜索作品", "如何搜索作品", "怎么搜索委托", "如何搜索委托",
    "怎么搜索灵感", "如何搜索灵感", "怎么发布委托", "如何发布委托",
    "怎么编辑委托", "如何编辑委托", "怎么删除委托", "如何删除委托",
    "怎么修改报价", "如何修改报价", "怎么更新报价", "如何更新报价",
    "怎么撤回报价", "如何撤回报价", "怎么选择报价", "如何选择报价",
    "怎么接受邀请", "如何接受邀请", "怎么拒绝邀请", "如何拒绝邀请",
    "怎么查看进度", "如何查看进度", "怎么放弃委托", "如何放弃委托",
    "怎么购买", "如何购买", "怎么付款", "如何付款", "怎么退款", "如何退款",
)

_PLATFORM_QUESTION_MARKERS = (
    "怎么",
    "怎样",
    "如何",
    "在哪",
    "哪里",
    "为什么",
    "为何",
    "能否",
    "可否",
    "能不能",
    "可不可以",
    "是否",
    "谁能",
    "谁可以",
    "谁可",
    "可以吗",
    "能吗",
    "行吗",
    "规则是什么",
    "有什么规则",
    "有限制吗",
    "怎么办",
)

_PLATFORM_SUBJECT_TERMS = (
    "作品",
    "画作",
    "委托",
    "约稿",
    "竞价",
    "报价",
    "成交价",
    "订单",
    "账号",
    "账户",
    "密码",
    "模型",
    "api",
    "apikey",
    "接口",
    "浏览历史",
)

_PLATFORM_ACTION_TERMS = (
    "发布",
    "上传",
    "编辑",
    "修改",
    "删除",
    "评价",
    "评论",
    "打分",
    "审核",
    "点赞",
    "收藏",
    "查看",
    "配置",
    "设置",
    "切换",
    "更新",
    "撤回",
    "选择",
    "接受",
    "拒绝",
    "付款",
    "支付",
    "退款",
    "购买",
    "注册",
    "登录",
    "注销",
    "找回",
    "重置",
    "邀请",
    "放弃",
    "关注",
    "隐藏",
    "公开",
    "可见",
    "接入",
    "连接",
    "操作",
    "规则",
    "流程",
    "限制",
    "权限",
    "入口",
)

_PLATFORM_STANDALONE_ACTIONS = (
    "点赞",
    "收藏",
    "浏览历史",
    "注册",
    "登录",
    "修改密码",
    "改密码",
    "找回密码",
    "重置密码",
    "付款",
    "支付",
    "退款",
)

_COMMISSION_SEARCH_HELP_PHRASES = (
    "怎么搜索委托",
    "怎样搜索委托",
    "如何搜索委托",
    "委托在哪搜索",
    "委托在哪里搜索",
    "委托搜索在哪",
    "委托搜索入口",
    "怎么查看开放委托",
    "怎样查看开放委托",
    "如何查看开放委托",
)


def _is_platform_help_question(compact):
    """Recognize questions about using the platform, not topic keywords alone."""
    if any(phrase in compact for phrase in _PLATFORM_HELP_PHRASES):
        return True

    has_question_marker = any(
        marker in compact for marker in _PLATFORM_QUESTION_MARKERS
    ) or compact.endswith(("吗", "么", "呢"))
    if not has_question_marker:
        return False

    if any(action in compact for action in _PLATFORM_STANDALONE_ACTIONS):
        return True

    # “谁能看成交价” is a visibility/permission question. Keep this
    # deliberately narrower than treating every occurrence of “看” as a
    # platform action, which would misroute ordinary chat such as
    # “你怎么看这幅作品”.
    has_visibility_question = any(
        subject in compact for subject in ("成交价", "报价", "订单")
    ) and any(
        phrase in compact
        for phrase in (
            "谁能看",
            "谁可以看",
            "谁可看",
            "能看到",
            "可以看到",
            "在哪看",
            "哪里看",
            "对谁可见",
            "谁可见",
        )
    )
    if has_visibility_question:
        return True

    has_platform_subject = any(
        subject in compact for subject in _PLATFORM_SUBJECT_TERMS
    )
    has_platform_action = any(
        action in compact for action in _PLATFORM_ACTION_TERMS
    )
    return has_platform_subject and has_platform_action


def extract_commission_query_terms(message):
    """Extract subject/style terms without treating commission verbs as tags."""
    text = str(message or "")
    for noise in _COMMISSION_QUERY_NOISE:
        text = text.replace(noise, " ")
    return extract_query_terms(text)


_SELF_DISCLOSURE_RE = re.compile(
    r"(?:我是(?:一个)?|我也是|作为(?:一个)?)(?P<topic>[^，。！？!?]{1,40}?)(?:的)?"
    r"(?:粉丝|玩家|爱好者|观众|读者)(?:$|[，。！？!?])"
)


def extract_conversation_topics(message):
    """Return explicit user interests that may ground a later recommendation."""
    match = _SELF_DISCLOSURE_RE.search(str(message or "").strip())
    if not match:
        return ()
    topic = match.group("topic").strip(" 《》「」『』\"'的")[:50]
    return (topic,) if topic else ()


def extract_refinement_terms(message):
    """Extract concise style/topic terms from recommendation follow-ups."""
    text = str(message or "").strip()
    match = re.search(
        r"(?:换成|改成|换为|改为|换个|来点|想看|要看)\s*([^，。！？!?]{1,40}?)(?:的)?(?:作品|画作|插画)?(?:$|[，。！？!?])",
        text,
    )
    if match:
        value = match.group(1).strip(" 《》「」『』\"'的")
        return (value[:50],) if value else ()

    # A short noun/style reply after a recommendation (for example “古风”)
    # is treated as a refinement by the view only when recommendation context
    # exists. Keeping that contextual guard out of this parser avoids turning
    # ordinary one-word chat into a catalogue search.
    compact = re.sub(r"[\s，。！？!?、~～]+", "", text)
    if 1 <= len(compact) <= 20 and re.fullmatch(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", compact):
        if compact not in {"谢谢", "谢谢你", "好的", "好", "嗯", "可以", "不用了"}:
            return extract_query_terms(compact)
    return ()


# Backwards-compatible private alias for callers/tests written before the
# contextual recommendation router was added.
_query_terms = extract_query_terms


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
    is_self_disclosure = bool(extract_conversation_topics(text))
    if is_topic_change:
        return IntentResult(INTENT_CONVERSATION)

    commission_subject_terms = ("委托", "约稿", "单子")
    artist_subject_terms = ("画师", "画家", "作者", "作家")
    commission_artist_match = (
        any(keyword in compact for keyword in commission_subject_terms)
        and any(keyword in compact for keyword in artist_subject_terms)
        and any(
            keyword in compact
            for keyword in ("匹配", "推荐", "适合", "符合", "谁能", "谁可以", "挑选", "找")
        )
        and any(
            keyword in compact
            for keyword in ("我的", "自己", "这个", "该", "最近", "发布", "第", "号委托", "委托#", "委托:", "委托：")
        )
    )
    if commission_artist_match:
        return IntentResult(INTENT_COMMISSION_ARTIST_MATCH)

    platform_help_question = _is_platform_help_question(compact)

    commission_search_phrases = (
        "适合我接的委托",
        "符合我接的委托",
        "适合我的委托",
        "符合我的委托",
        "适合自己的委托",
        "符合自己的委托",
        "我能接的委托",
        "可以接的委托",
        "能接的委托",
        "有什么委托可以接",
        "有哪些委托可以接",
        "推荐委托",
        "查找委托",
        "搜索委托",
        "搜委托",
        "找委托",
        "找约稿",
        "找单子",
        "接什么单",
        "接哪些单",
    )
    commission_search = any(phrase in compact for phrase in commission_search_phrases) or (
        any(keyword in compact for keyword in commission_subject_terms)
        and any(keyword in compact for keyword in ("推荐", "搜索", "搜", "查找", "找"))
        and any(keyword in compact for keyword in ("接", "适合", "符合", "开放"))
    )
    commission_search_how_to = any(
        phrase in compact for phrase in _COMMISSION_SEARCH_HELP_PHRASES
    )
    if commission_search and not commission_search_how_to:
        return IntentResult(
            INTENT_COMMISSION_SEARCH,
            query_terms=extract_commission_query_terms(text),
            min_price=min_price,
            max_price=max_price,
        )

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

    if platform_help_question:
        return IntentResult(INTENT_PLATFORM_HELP)

    commission_terms = ("委托", "约稿", "竞价", "报价", "接单")
    invitation_context_terms = ("画师", "画家", "作家", "作画", "接稿", "定向")
    if any(keyword in compact for keyword in commission_terms) or (
        "邀请" in compact
        and any(keyword in compact for keyword in invitation_context_terms)
    ):
        return IntentResult(INTENT_COMMISSION)

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
