import json
import re
from urllib import error, request as urlrequest
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.artworks.models import Artwork
from apps.custom.models import CustomRequest
from common.response import fail, ok

from .serializers import AIChatSerializer


SYSTEM_PROMPT = """你是“星漫 AI 创作助手”，服务于动漫创作社区。请始终使用简洁、友善的中文回答。
你可以：1. 日常聊天；2. 根据用户需求推荐站内画师、作品和委托；3. 提供原创创意、构图、角色、剧情和配色灵感。
推荐时只使用下方提供的站内资料，不要虚构用户、作品、作者、价格或委托；资料不足时明确说明，并给出可执行的筛选建议。
作品作者必须严格使用 artist_username 字段，绝对不能根据作品题材猜测作者。画师只能从 artists 中选择。
推荐作品时不要在正文中自行描述作者，作者信息统一由下方数据库预览卡展示。
每次提到站内实体时必须附带其引用标记，格式只能是【作品#数字ID】、【画师#数字ID】或【委托#数字ID】。标记中的 ID 必须来自资料。
不要声称已经替用户下单、联系画师或完成任何站内操作。"""

ART_APPRECIATION_PROMPT = """
你同时是一位专业、严谨且善于教学的美术鉴赏顾问。遇到作品图片、画风、艺术家、流派、技法、艺术史或审美分析问题时：
1. 先区分“画面中可直接观察到的事实”和“基于艺术史知识的推断”，不确定之处必须使用“可能、接近、让人联想到”等措辞。
2. 从主题与视觉叙事、构图、造型与线条、色彩与明度、光影、空间与透视、材质与笔触、节奏与视觉重心逐项深入分析。
3. 解释可能使用的媒介、技法、风格谱系和相关术语，并给初学者可理解的定义；不得仅堆砌风格标签。
4. 可以比较相近流派或艺术家的共性与差异，但不能仅凭画风断言作者身份、真伪、年代或作品价值。
5. 最后总结作品的视觉效果、情绪表达、值得学习之处和可执行的创作练习。
6. 使用网络资料时优先采用博物馆、美术馆、大学、艺术家基金会和权威百科资料，事实性陈述注明对应来源编号。
如果用户上传图片，就以该图片的视觉证据为分析核心；图片细节不足时明确指出限制。"""

ART_SEARCH_PATTERN = re.compile(
    r"美术|鉴赏|赏析|画风|风格|流派|艺术家|画家|艺术史|构图|色彩|光影|笔触|技法|媒介|油画|水彩|版画|插画|雕塑|"
    r"印象派|表现主义|现实主义|浪漫主义|文艺复兴|巴洛克|洛可可|现代主义|后现代|浮世绘|国画|水墨|"
    r"莫奈|梵高|毕加索|达芬奇|米开朗基罗|拉斐尔|伦勃朗|维米尔|塞尚|高更|马蒂斯|搜索|联网|资料|背景"
)


def _site_context():
    User = get_user_model()
    artists = []
    for user in (
        User.objects.filter(is_active=True, artworks__isnull=False)
        .distinct()
        .only("id", "username", "bio", "profile")
        .order_by("username")[:30]
    ):
        profile = user.profile if isinstance(user.profile, dict) else {}
        skills = profile.get("skills", [])
        artists.append({
            "id": user.id,
            "username": user.username,
            "display_name": profile.get("displayName") or user.username,
            "bio": user.bio[:240],
            "skills": skills[:8] if isinstance(skills, list) else [],
            "artworks": list(user.artworks.order_by("-created_at").values_list("title", flat=True)[:8]),
        })
    artworks = [
        {
            "id": item.id,
            "title": item.title,
            "artist_id": item.owner_id,
            "artist_username": item.owner.username,
            "category": item.category,
            "tags": item.tags,
            "price": str(item.price),
        }
        for item in Artwork.objects.filter(is_available=True).select_related("owner").order_by("-created_at")[:40]
    ]
    commissions = [
        {
            "id": item.id,
            "title": item.title,
            "type": item.type_label,
            "budget": str(item.budget),
            "budget_note": item.budget_note,
            "requester": item.requester.username,
        }
        for item in CustomRequest.objects.filter(status=CustomRequest.Status.SUBMITTED)
        .select_related("requester").order_by("-created_at")[:30]
    ]
    return json.dumps(
        {"artists": artists, "available_artworks": artworks, "open_commissions": commissions},
        ensure_ascii=False,
        default=str,
    )


def _avatar_url(user):
    if user.avatar:
        return user.avatar.url
    profile = user.profile if isinstance(user.profile, dict) else {}
    return profile.get("avatar", "")


def _recommendation_entities(answer, query):
    """Resolve model references against the database; never trust model-authored metadata."""
    marker_ids = {"artwork": [], "artist": [], "commission": []}
    marker_types = {"作品": "artwork", "画师": "artist", "委托": "commission"}
    for label, raw_id in re.findall(r"【(作品|画师|委托)#(\d+)】", answer):
        marker_ids[marker_types[label]].append(int(raw_id))

    artworks = list(Artwork.objects.filter(is_available=True).select_related("owner").order_by("-created_at")[:40])
    artist_ids = {item.owner_id for item in artworks}
    User = get_user_model()
    artists = list(User.objects.filter(id__in=artist_ids, is_active=True).order_by("username"))
    commissions = list(
        CustomRequest.objects.filter(status=CustomRequest.Status.SUBMITTED)
        .select_related("requester").order_by("-created_at")[:30]
    )

    # Also resolve exact names mentioned by the model. This is a compatibility fallback
    # for providers that occasionally omit the requested markers.
    marker_ids["artwork"].extend(item.id for item in artworks if item.title and item.title in answer)
    marker_ids["artist"].extend(item.id for item in artists if item.username and item.username in answer)
    marker_ids["commission"].extend(item.id for item in commissions if item.title and item.title in answer)

    if not any(marker_ids.values()):
        if "画师" in query or "作者" in query:
            marker_ids["artist"] = [item.id for item in artists[:6]]
        elif "作品" in query or "画" in query:
            marker_ids["artwork"] = [item.id for item in artworks[:6]]
        elif "委托" in query or "接单" in query:
            marker_ids["commission"] = [item.id for item in commissions[:6]]

    selected = []
    seen = set()
    artwork_map = {item.id: item for item in artworks}
    artist_map = {item.id: item for item in artists}
    commission_map = {item.id: item for item in commissions}
    for entity_type in ("artist", "artwork", "commission"):
        for entity_id in marker_ids[entity_type]:
            key = (entity_type, entity_id)
            if key in seen or len(selected) >= 8:
                continue
            seen.add(key)
            if entity_type == "artwork" and (item := artwork_map.get(entity_id)):
                selected.append({
                    "type": "artwork", "id": item.id, "title": item.title,
                    "subtitle": f"作者：{item.owner.username} · {item.category or '原创作品'}",
                    "image_url": item.image.url if item.image else "",
                    "artist_username": item.owner.username,
                })
            elif entity_type == "artist" and (item := artist_map.get(entity_id)):
                profile = item.profile if isinstance(item.profile, dict) else {}
                selected.append({
                    "type": "artist", "id": item.id,
                    "title": profile.get("displayName") or item.username,
                    "subtitle": f"@{item.username} · {item.bio[:80] or '站内画师'}",
                    "image_url": _avatar_url(item), "username": item.username,
                })
            elif entity_type == "commission" and (item := commission_map.get(entity_id)):
                selected.append({
                    "type": "commission", "id": item.id, "title": item.title,
                    "subtitle": f"{item.type_label or '委托'} · 预算 ¥{item.budget} · @{item.requester.username}",
                    "image_url": item.reference_image.url if item.reference_image else "",
                })
    return selected


def _should_search_web(message, has_image=False):
    return bool(has_image or ART_SEARCH_PATTERN.search(message))


def _web_search_tool():
    return {
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_std",
            "search_result": True,
            "count": 6,
            "search_recency_filter": "noLimit",
            "content_size": "high",
            "search_prompt": (
                "你是美术史资料研究助手。请从网络搜索结果{search_result}中筛选可靠信息，优先博物馆、美术馆、大学、"
                "艺术家基金会与权威百科；明确区分史实、评论和推断，并在相关内容后使用[来源: ref_n]标注。"
            ),
        },
    }


def _web_sources(result):
    sources = []
    seen = set()
    for item in result.get("web_search", []) or []:
        link = str(item.get("link", "")).strip()
        parsed = urlparse(link)
        if not link or parsed.scheme not in {"http", "https"} or link in seen:
            continue
        seen.add(link)
        sources.append({
            "title": str(item.get("title", "")).strip() or parsed.netloc,
            "url": link,
            "site": str(item.get("media", "")).strip() or parsed.netloc,
            "published_at": str(item.get("publish_date", "")).strip(),
            "snippet": str(item.get("content", "")).strip()[:280],
            "reference": str(item.get("refer", "")).strip(),
        })
        if len(sources) >= 8:
            break
    return sources


class AIStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return ok({
            "available": bool(settings.AI_API_KEY),
            "api_base": settings.AI_API_BASE,
            "model": settings.AI_MODEL,
            "vision_model": settings.AI_VISION_MODEL,
        })


class AIChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "ai_chat"

    def post(self, request):
        serializer = AIChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        api_key = data.get("api_key") or settings.AI_API_KEY
        api_base = (data.get("api_base") or settings.AI_API_BASE).rstrip("/")
        image_data = data.get("image_data", "")
        model = (data.get("vision_model") or settings.AI_VISION_MODEL) if image_data else (data.get("model") or settings.AI_MODEL)
        if not api_key:
            return fail("AI 服务尚未配置，请在助手设置中填写 API Key。", code=503, status=503)

        system_content = SYSTEM_PROMPT + ART_APPRECIATION_PROMPT + "\n\n当前站内资料：\n" + _site_context()
        user_content = data["message"]
        if image_data:
            user_content = [
                {"type": "text", "text": data["message"]},
                {"type": "image_url", "image_url": {"url": image_data}},
            ]
        messages = [
            {"role": "system", "content": system_content},
            *data["history"],
            {"role": "user", "content": user_content},
        ]
        request_payload = {"model": model, "messages": messages, "temperature": 0.65, "max_tokens": 3000}
        # Zhipu's web_search tool is provider-specific. Custom OpenAI-compatible
        # endpoints still receive normal chat requests without unsupported fields.
        web_enabled = _should_search_web(data["message"], bool(image_data)) and urlparse(api_base).hostname in {
            "open.bigmodel.cn", "api.z.ai"
        }
        if web_enabled:
            request_payload.update({"tools": [_web_search_tool()], "tool_choice": "auto"})
        payload = json.dumps(request_payload).encode("utf-8")
        http_request = urlrequest.Request(
            f"{api_base}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(http_request, timeout=settings.AI_REQUEST_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            clean_content = re.sub(r"【(?:作品|画师|委托)#\d+】", "", content).strip()
            return ok({
                "message": clean_content,
                "model": result.get("model", model),
                "recommendations": _recommendation_entities(content, data["message"]),
                "sources": _web_sources(result),
                "web_search_used": web_enabled,
            })
        except error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                detail = ""
            return fail(detail or "大模型服务拒绝了请求，请检查 API 配置。", code=502, status=502)
        except (error.URLError, TimeoutError):
            return fail("暂时无法连接大模型服务，请稍后重试。", code=504, status=504)
        except (KeyError, ValueError, json.JSONDecodeError):
            return fail("大模型返回了无法识别的数据。", code=502, status=502)
