"""Safe, deterministic commission and artist matching for the AI assistant.

This module deliberately returns small dictionaries instead of model instances or
serializer output.  That keeps private bid/invitation data out of model prompts and
makes the service safe to reuse from both local and provider-backed replies.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable

from django.db.models import Count, Prefetch, Q

from apps.artworks.models import Artwork
from apps.custom.models import CommissionBid, CommissionInvitation, CustomRequest


MAX_SCAN_COMMISSIONS = 500
MAX_SCAN_ARTWORKS = 1000
MAX_RESULT_LIMIT = 50

__all__ = [
    "extract_commission_reference",
    "matching_artists_for_owned_commission",
    "matching_open_commissions",
    "owned_open_commission",
]


def _normalized(value) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _limited_text(value, maximum: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maximum]


def _safe_limit(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, 1), MAX_RESULT_LIMIT)


def _safe_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _safe_terms(values: Iterable[object] | object, *, limit: int = 30) -> list[str]:
    if isinstance(values, str):
        raw_values = re.split(r"[,，、/|#\s]+", values)
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = []

    terms: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        value = _limited_text(raw_value, 50)
        key = _normalized(value)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        terms.append(value)
        if len(terms) >= limit:
            break
    return terms


def _profile_list_terms(value, *, limit: int) -> list[str]:
    # User.profile has no schema at the model layer.  Public profile serializers
    # already treat non-list skills as invalid, and matching follows that rule.
    if not isinstance(value, (list, tuple, set)):
        return []
    return _safe_terms(value, limit=limit)


def _profile_terms(user) -> tuple[list[str], list[str]]:
    profile = user.profile if isinstance(user.profile, dict) else {}
    skills = _profile_list_terms(profile.get("skills", []), limit=20)
    preferences = _profile_list_terms(
        profile.get("homeTags") or profile.get("recommendationTags") or [],
        limit=20,
    )
    return skills, preferences


def _artwork_tags(artwork) -> list[str]:
    raw_tags = artwork.tags if isinstance(artwork.tags, list) else [artwork.tags]
    return _safe_terms(raw_tags, limit=10)


def _open_commission_filter() -> Q:
    """Match exactly the invariant enforced by CustomRequestViewSet._ensure_open."""

    return Q(
        status=CustomRequest.Status.SUBMITTED,
        artist__isnull=True,
        selected_bid__isnull=True,
        agreed_price__isnull=True,
    )


def _own_candidate_state(commission) -> tuple[str | None, str | None]:
    bids = getattr(commission, "_matching_my_bids", [])
    invitations = getattr(commission, "_matching_my_invitations", [])
    bid_status = bids[0].status if bids else None
    invitation_status = invitations[0].status if invitations else None
    return bid_status, invitation_status


def _commission_payload(commission, score: float, *, description_limit: int = 300) -> dict:
    bid_status, invitation_status = _own_candidate_state(commission)
    return {
        "id": commission.id,
        "title": _limited_text(commission.title, 120),
        "type_label": _limited_text(commission.type_label, 80),
        "description": _limited_text(commission.description, description_limit),
        "budget": str(commission.budget),
        "budget_note": _limited_text(commission.budget_note, 80),
        "status": CustomRequest.Status.SUBMITTED,
        "bid_count": int(getattr(commission, "active_bid_count", 0) or 0),
        "my_bid_status": bid_status,
        "my_invitation_status": invitation_status,
        "created_at": commission.created_at.isoformat(),
        "match_score": round(float(score), 3),
    }


def matching_open_commissions(
    user,
    *,
    query_terms: Iterable[object] | object = (),
    min_budget=None,
    max_budget=None,
    limit: int = 20,
) -> list[dict]:
    """Return open commissions matching the current user's public expertise.

    Only the current user's own bid/invitation status is prefetched.  Other
    candidates' prices, messages, and invitation details never enter memory or the
    returned payload.
    """

    result_limit = _safe_limit(limit, 20)
    explicit_terms = _safe_terms(query_terms)
    skills, preferences = _profile_terms(user)

    expertise_terms: list[str] = []
    seen_expertise: set[str] = set()
    for value in [*skills, *preferences]:
        key = _normalized(value)
        if key and key not in seen_expertise:
            seen_expertise.add(key)
            expertise_terms.append(value)

    own_artworks = Artwork.objects.filter(owner=user, is_available=True).only(
        "category", "tags"
    )[:200]
    for artwork in own_artworks:
        for value in _safe_terms([artwork.category, *_artwork_tags(artwork)]):
            key = _normalized(value)
            if key and key not in seen_expertise:
                seen_expertise.add(key)
                expertise_terms.append(value)
                if len(expertise_terms) >= 60:
                    break
        if len(expertise_terms) >= 60:
            break

    # Without public evidence or an explicit request there is no defensible basis
    # for claiming that a commission is suitable for this user.
    if not explicit_terms and not expertise_terms:
        return []

    queryset = (
        CustomRequest.objects.filter(_open_commission_filter(), requester__is_active=True)
        .exclude(requester=user)
        .select_related("requester")
        .annotate(
            active_bid_count=Count(
                "bids",
                filter=Q(bids__status=CommissionBid.Status.ACTIVE),
                distinct=True,
            )
        )
        .prefetch_related(
            Prefetch(
                "bids",
                queryset=CommissionBid.objects.filter(artist=user).only(
                    "id", "custom_request_id", "status"
                ),
                to_attr="_matching_my_bids",
            ),
            Prefetch(
                "invitations",
                queryset=CommissionInvitation.objects.filter(artist=user).only(
                    "id", "custom_request_id", "status"
                ),
                to_attr="_matching_my_invitations",
            ),
        )
    )
    minimum = _safe_decimal(min_budget)
    maximum = _safe_decimal(max_budget)
    if minimum is not None:
        queryset = queryset.filter(budget__gte=minimum)
    if maximum is not None:
        queryset = queryset.filter(budget__lte=maximum)

    ranked: list[tuple[CustomRequest, float, bool, bool]] = []
    for commission in queryset.order_by("-created_at", "-id")[:MAX_SCAN_COMMISSIONS]:
        title = _normalized(commission.title)
        type_label = _normalized(commission.type_label)
        description = _normalized(commission.description)
        haystack = f"{title} {type_label} {description}"

        explicit_score = 0.0
        for raw_term in explicit_terms:
            term = _normalized(raw_term)
            if term in type_label:
                explicit_score += 120
            elif term in title:
                explicit_score += 100
            elif term in description:
                explicit_score += 60
        if explicit_terms and explicit_score <= 0:
            continue

        expertise_score = 0.0
        for raw_term in expertise_terms:
            term = _normalized(raw_term)
            if not term:
                continue
            if term in type_label:
                expertise_score += 55
            elif term in title:
                expertise_score += 45
            elif term in description:
                expertise_score += 25
        if not explicit_terms and expertise_score <= 0:
            continue

        bid_status, invitation_status = _own_candidate_state(commission)
        pending_invitation = invitation_status == CommissionInvitation.Status.PENDING
        has_active_bid = bid_status == CommissionBid.Status.ACTIVE
        score = explicit_score + expertise_score + (20 if pending_invitation else 0)
        ranked.append((commission, score, pending_invitation, has_active_bid))

    ranked.sort(
        key=lambda item: (
            item[1],
            item[2],
            not item[3],
            item[0].budget,
            item[0].created_at,
            item[0].id,
        ),
        reverse=True,
    )
    return [
        _commission_payload(commission, score)
        for commission, score, _, _ in ranked[:result_limit]
    ]


def extract_commission_reference(message) -> int | None:
    """Extract only explicit commission references, never a bare budget number."""

    text = str(message or "")
    patterns = (
        r"\[委托\s*[:：]\s*(\d+)\s*\]",
        r"委托\s*[#＃:]?\s*(\d+)\s*号",
        r"(?:第\s*)?(\d+)\s*号委托",
        r"委托\s*[#＃:：]\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
    return None


def _owned_open_commission(user, commission_id=None):
    queryset = CustomRequest.objects.filter(
        _open_commission_filter(), requester=user
    ).annotate(
        active_bid_count=Count(
            "bids",
            filter=Q(bids__status=CommissionBid.Status.ACTIVE),
            distinct=True,
        )
    )
    if commission_id not in (None, ""):
        try:
            value = int(commission_id)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return queryset.filter(pk=value).first()
    return queryset.order_by("-created_at", "-id").first()


def owned_open_commission(user, commission_id=None) -> dict | None:
    """Resolve an explicit or latest commission only inside the user's own scope."""

    commission = _owned_open_commission(user, commission_id)
    if commission is None:
        return None
    return _commission_payload(commission, 0, description_limit=500)


def _artist_display_name(artist) -> str:
    profile = artist.profile if isinstance(artist.profile, dict) else {}
    return _limited_text(
        profile.get("displayName") or artist.get_full_name() or artist.username,
        120,
    )


def matching_artists_for_owned_commission(
    user,
    *,
    commission_id=None,
    limit: int = 10,
) -> dict:
    """Match active artists for the user's own open commission.

    Eligibility requires at least one public, currently available artwork.  The
    result intentionally excludes email, full profile JSON, bids, invitations,
    selected bids, and agreed prices.
    """

    commission = _owned_open_commission(user, commission_id)
    if commission is None:
        return {"commission": None, "artists": []}

    source_text = _normalized(
        " ".join(
            [commission.title, commission.type_label, commission.description]
        )
    )
    grouped: dict[int, dict] = {}
    artworks = (
        Artwork.objects.filter(is_available=True, owner__is_active=True)
        .exclude(owner=user)
        .select_related("owner")
        .annotate(reviews_total=Count("reviews", distinct=True))
        .order_by("-created_at", "-id")[:MAX_SCAN_ARTWORKS]
    )
    for artwork in artworks:
        artist = artwork.owner
        profile = artist.profile if isinstance(artist.profile, dict) else {}
        skills = _profile_list_terms(profile.get("skills", []), limit=20)
        categories = _safe_terms([artwork.category], limit=1)
        tags = _artwork_tags(artwork)
        entry = grouped.setdefault(
            artist.id,
            {
                "artist": artist,
                "skills": skills,
                "categories": [],
                "tags": [],
                "work_count": 0,
                "reviews_count": 0,
                "score": 0.0,
                "matched": set(),
            },
        )

        # A profile can change between artworks; merge sanitized public values.
        entry["skills"] = _safe_terms([*entry["skills"], *skills], limit=20)
        entry["categories"] = _safe_terms(
            [*entry["categories"], *categories], limit=5
        )
        entry["tags"] = _safe_terms([*entry["tags"], *tags], limit=10)
        entry["work_count"] += 1
        entry["reviews_count"] += int(getattr(artwork, "reviews_total", 0) or 0)

        evidence = (
            [(value, 110) for value in skills]
            + [(value, 95) for value in categories]
            + [(value, 85) for value in tags]
            + [(artwork.title, 45)]
        )
        for raw_value, weight in evidence:
            value = _normalized(raw_value)
            if len(value) >= 2 and value in source_text and value not in entry["matched"]:
                entry["matched"].add(value)
                entry["score"] += weight

    ranked = [entry for entry in grouped.values() if entry["score"] > 0]
    ranked.sort(
        key=lambda entry: (
            entry["score"],
            entry["work_count"],
            entry["reviews_count"],
            entry["artist"].id,
        ),
        reverse=True,
    )

    artists = []
    for entry in ranked[: _safe_limit(limit, 10)]:
        artist = entry["artist"]
        artists.append(
            {
                "id": artist.id,
                "username": _limited_text(artist.username, 150),
                "display_name": _artist_display_name(artist),
                "bio": _limited_text(artist.bio, 200),
                "skills": entry["skills"],
                "categories": entry["categories"],
                "tags": entry["tags"],
                "available_work_count": entry["work_count"],
                "reviews_count": entry["reviews_count"],
                "match_score": round(float(entry["score"]), 3),
            }
        )

    return {
        "commission": _commission_payload(commission, 0, description_limit=500),
        "artists": artists,
    }
