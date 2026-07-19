import json
import re
from urllib import error, request as urlrequest

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.artworks.models import Artwork
from apps.custom.models import CommissionBid, CustomRequest

User = get_user_model()


def _extract_artist_features(user):
    profile = user.profile if isinstance(user.profile, dict) else {}
    artworks = list(user.artworks.filter(is_available=True).select_related("owner"))

    categories = set()
    tags = set()
    prices = []

    for artwork in artworks:
        if artwork.category:
            categories.add(artwork.category)
        if isinstance(artwork.tags, list):
            tags.update(artwork.tags)
        if artwork.price > 0:
            prices.append(float(artwork.price))

    completed_bids = CommissionBid.objects.filter(
        artist=user,
        status=CommissionBid.Status.SELECTED
    ).count()

    return {
        "id": user.id,
        "username": user.username,
        "display_name": profile.get("displayName") or user.username,
        "bio": user.bio[:200] if user.bio else "",
        "skills": profile.get("skills", [])[:10] if isinstance(profile.get("skills"), list) else [],
        "styles": list(categories),
        "tags": list(tags)[:20],
        "price_range": {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0
        },
        "work_count": len(artworks),
        "completed_count": completed_bids
    }


def _pre_filter_artists(custom_request, limit=20):
    queryset = User.objects.filter(
        is_active=True,
        artworks__isnull=False
    ).distinct()

    if custom_request.type_label:
        type_keywords = [kw.strip() for kw in custom_request.type_label.split('/') if kw.strip()]
        for keyword in type_keywords[:3]:
            queryset = queryset.filter(
                Q(artworks__category__icontains=keyword) |
                Q(artworks__tags__contains=[keyword])
            )

    if custom_request.budget and custom_request.budget > 0:
        budget_value = float(custom_request.budget)
        min_price = budget_value * 0.3
        max_price = budget_value * 2.0
        queryset = queryset.filter(
            artworks__price__gte=min_price,
            artworks__price__lte=max_price
        )

    description = custom_request.description or ""
    keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', description)[:10]
    if keywords:
        tag_filter = Q()
        for kw in keywords:
            tag_filter |= Q(artworks__tags__contains=[kw]) | Q(bio__icontains=kw)
        queryset = queryset.filter(tag_filter)

    return list(queryset[:limit])


def _build_prompt(custom_request, artists):
    prompt = f"""你是一位专业的动漫委托匹配顾问。请根据以下委托需求，从提供的画师列表中推荐最合适的画师。

## 委托需求
- 标题: {custom_request.title}
- 类型: {custom_request.type_label or '未指定'}
- 描述: {custom_request.description[:800]}
- 预算: {custom_request.budget_note or str(custom_request.budget)}
- 是否有参考图: {'是' if custom_request.reference_image else '否'}

## 匹配要求
1. 优先匹配画风、风格与需求描述相符的画师
2. 考虑画师的技能标签与需求的相关性
3. 综合评价匹配度，返回 0-100 的置信度分数
4. 最多推荐 10 位画师，按匹配度从高到低排序
5. 匹配理由需简洁明了，说明推荐依据

## 画师列表
{json.dumps(artists, ensure_ascii=False, default=str)}

## 输出格式
请严格按照 JSON 格式输出，不要包含任何其他文字：
[
  {{"artist_id": 数字ID, "confidence": 匹配度(0-100), "reason": "匹配理由"}}
]"""
    return prompt


def _call_ai(prompt):
    api_key = settings.AI_API_KEY
    api_base = settings.AI_API_BASE.rstrip("/")

    if not api_key:
        raise ValueError("AI API Key 未配置")

    messages = [
        {"role": "system", "content": "你是一位专业的动漫委托匹配顾问，擅长根据画风、技能和需求进行精准匹配。"},
        {"role": "user", "content": prompt}
    ]

    request_payload = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }

    payload = json.dumps(request_payload).encode("utf-8")
    http_request = urlrequest.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlrequest.urlopen(http_request, timeout=settings.AI_REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"].strip()
        return content
    except error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise ValueError(f"AI 服务拒绝请求: {detail}")
    except (error.URLError, TimeoutError):
        raise ValueError("无法连接 AI 服务，请稍后重试")
    except (KeyError, ValueError, json.JSONDecodeError):
        raise ValueError("AI 返回数据格式错误")


def _parse_ai_result(content):
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)

    try:
        match = re.search(r"\[[\s\S]*\]", content)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(content)
        return data
    except json.JSONDecodeError:
        raise ValueError("无法解析 AI 返回的匹配结果")


def _fallback_tag_matching(custom_request, artists):
    description = custom_request.description or ""
    type_label = custom_request.type_label or ""

    all_keywords = set()
    all_keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', description)[:15])
    all_keywords.update(re.findall(r'[a-zA-Z]+', description)[:10])
    if type_label:
        all_keywords.update([kw.strip() for kw in type_label.split('/') if kw.strip()])

    if not all_keywords:
        all_keywords = {"插画", "动漫", "原创"}

    results = []
    for artist in artists:
        match_count = 0
        total_tags = set()

        for tag in artist.get("styles", []):
            total_tags.add(tag)
            if any(kw in tag for kw in all_keywords):
                match_count += 2

        for tag in artist.get("tags", []):
            total_tags.add(tag)
            if any(kw in tag for kw in all_keywords):
                match_count += 1

        for skill in artist.get("skills", []):
            total_tags.add(skill)
            if any(kw in skill for kw in all_keywords):
                match_count += 1

        if artist.get("bio"):
            for kw in all_keywords:
                if kw in artist["bio"]:
                    match_count += 1

        max_score = len(total_tags) * 2 + len(all_keywords)
        confidence = min(int((match_count / max_score) * 100) if max_score > 0 else 0, 100)

        if confidence > 0:
            matched_tags = [t for t in total_tags if any(kw in t for kw in all_keywords)]
            reason = f"标签匹配: {', '.join(matched_tags[:5])}"
            results.append({
                "artist_id": artist["id"],
                "confidence": confidence,
                "reason": reason
            })

    return sorted(results, key=lambda x: x["confidence"], reverse=True)[:10]


def _get_sample_works(artist_id, limit=3):
    works = Artwork.objects.filter(
        owner_id=artist_id,
        is_available=True
    ).order_by("-created_at")[:limit]

    return [{
        "id": work.id,
        "title": work.title,
        "image": work.image.url if work.image else "",
        "category": work.category or "原创作品"
    } for work in works]


def match_artists(custom_request, limit=10):
    active_artists = _pre_filter_artists(custom_request, limit=25)

    if not active_artists:
        return {"recommendations": [], "total_candidates": 0, "used_fallback": False}

    artists = [_extract_artist_features(user) for user in active_artists]

    prompt = _build_prompt(custom_request, artists)

    try:
        ai_response = _call_ai(prompt)
        raw_results = _parse_ai_result(ai_response)
        used_fallback = False
    except ValueError:
        raw_results = _fallback_tag_matching(custom_request, artists)
        used_fallback = True

    artist_map = {a["id"]: a for a in artists}
    valid_results = []

    for result in raw_results[:limit]:
        artist_id = result.get("artist_id")
        if artist_id not in artist_map:
            continue

        artist_info = artist_map[artist_id]
        user = User.objects.filter(id=artist_id, is_active=True).first()
        if not user:
            continue

        valid_results.append({
            "artist": {
                "id": user.id,
                "username": user.username,
                "display_name": artist_info["display_name"],
                "avatar": user.avatar.url if user.avatar else "",
                "bio": artist_info["bio"],
                "skills": artist_info["skills"]
            },
            "confidence": result.get("confidence", 0),
            "reason": result.get("reason", ""),
            "sample_works": _get_sample_works(artist_id),
            "price_range": artist_info["price_range"]
        })

    return {
        "recommendations": sorted(valid_results, key=lambda x: x["confidence"], reverse=True),
        "total_candidates": len(artists),
        "used_fallback": used_fallback
    }