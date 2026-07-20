import hashlib
import math
import re

from django.db.models import Count
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from common.caching import CachedPublicReadMixin
from common.response import ApiResponseMixin

from .models import Artwork
from .serializers import ArtworkSerializer


class ArtworkViewSet(CachedPublicReadMixin, ApiResponseMixin, viewsets.ModelViewSet):
    serializer_class = ArtworkSerializer
    filterset_fields = ["owner", "category", "is_available"]
    search_fields = ["title", "description", "category"]
    ordering_fields = ["created_at", "updated_at", "price"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Artwork.objects.select_related("owner").annotate(reviews_total=Count("reviews")).all()

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _ensure_owner_or_admin(self, obj):
        if self.request.user.is_admin or obj.owner_id == self.request.user.id:
            return
        raise PermissionDenied("Only the owner or admin can modify this artwork.")

    def perform_update(self, serializer):
        self._ensure_owner_or_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner_or_admin(instance)
        instance.delete()

    @action(detail=False, methods=["get", "post"])
    def recommendations(self, request):
        payload = self._recommendation_payload(request)
        artworks = list(self.filter_queryset(self.get_queryset()))
        scores, matched_tags, recommendation_meta = self._score_artworks(artworks, payload)
        artworks = self._diversity_rerank(artworks, scores)

        page = self.paginate_queryset(artworks)
        items = page if page is not None else artworks
        data = [dict(item) for item in self.get_serializer(items, many=True).data]
        for item in data:
            key = str(item["id"])
            item["recommendation_score"] = round(scores.get(key, 0), 3)
            item["matched_tags"] = sorted(matched_tags.get(key, set()))
            item.update(recommendation_meta.get(key, {}))

        if page is not None:
            return self.get_paginated_response(data)
        return data

    def _recommendation_payload(self, request):
        source = request.data if request.method == "POST" else request.query_params
        profile_tags = []
        if request.user.is_authenticated:
            profile = request.user.profile if isinstance(request.user.profile, dict) else {}
            profile_tags = profile.get("homeTags") or profile.get("recommendationTags") or []

        return {
            "tags": self._tag_list(source.get("tags") or profile_tags),
            "views": self._count_map(source.get("views")),
            "likes": self._count_map(source.get("likes")),
            "favorites": self._count_map(source.get("favorites")),
            "comments": self._count_map(source.get("comments")),
            "impressions": self._count_map(source.get("impressions")),
            "dwell": self._count_map(source.get("dwell")),
            "history": self._history_list(source.get("history")),
            "dislikes": set(self._history_list(source.get("dislikes"))),
            "seed": str(source.get("seed") or getattr(request.user, "username", "") or "anonymous")[:80],
            "mode": "guess" if source.get("mode") == "guess" else "feed",
        }

    def _tag_list(self, value):
        if isinstance(value, str):
            parts = re.split(r"[,，、/|#\s]+", value)
        elif isinstance(value, (list, tuple, set)):
            parts = []
            for item in value:
                parts.extend(self._tag_list(item))
        else:
            parts = []

        tags = []
        seen = set()
        for part in parts:
            tag = str(part).strip().lower()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
        return tags[:20]

    def _count_map(self, value):
        if isinstance(value, dict):
            items = value.items()
        elif isinstance(value, (list, tuple, set)):
            items = ((item, 1) for item in value)
        else:
            return {}

        counts = {}
        for raw_id, raw_count in items:
            artwork_id = self._artwork_id(raw_id)
            if not artwork_id:
                continue
            try:
                count = float(raw_count or 0)
            except (TypeError, ValueError):
                count = 1
            counts[artwork_id] = max(0, count)
        return counts

    def _history_list(self, value):
        if not isinstance(value, (list, tuple, set)):
            return []
        history = []
        for item in value:
            artwork_id = self._artwork_id(item)
            if artwork_id:
                history.append(artwork_id)
        return history[:100]

    def _artwork_id(self, value):
        text = str(value or "").strip()
        if text.startswith("artwork:"):
            text = text.split(":", 1)[1]
        return text

    def _artwork_tags(self, artwork):
        raw_tags = artwork.tags or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        tags = self._tag_list([artwork.category, *raw_tags])
        return tags

    def _artwork_text(self, artwork):
        tags = " ".join(self._artwork_tags(artwork))
        return f"{artwork.title} {artwork.description} {artwork.category} {tags}".lower()

    def _score_artworks(self, artworks, payload):
        explicit_tags = payload["tags"]
        explicit_weights = {tag: max(1, len(explicit_tags) - index) for index, tag in enumerate(explicit_tags)}
        by_id = {str(artwork.id): artwork for artwork in artworks}
        behavior_weights = {}
        negative_weights = {}

        for artwork_id, count in payload["views"].items():
            self._add_behavior_weight(by_id.get(artwork_id), min(count, 8) * 1.0, behavior_weights)
        for artwork_id, count in payload["likes"].items():
            self._add_behavior_weight(by_id.get(artwork_id), min(count, 3) * 4.0, behavior_weights)
        for artwork_id, count in payload["favorites"].items():
            self._add_behavior_weight(by_id.get(artwork_id), min(count, 3) * 6.0, behavior_weights)
        for artwork_id, seconds in payload["dwell"].items():
            self._add_behavior_weight(
                by_id.get(artwork_id), min(math.log1p(seconds) * 1.6, 10), behavior_weights
            )
        for index, artwork_id in enumerate(payload["history"]):
            self._add_behavior_weight(by_id.get(artwork_id), max(0.5, 3.0 - index * 0.08), behavior_weights)
        for artwork_id in payload["dislikes"]:
            self._add_behavior_weight(by_id.get(artwork_id), 8.0, negative_weights)

        scores = {}
        matched_tags = {}
        recommendation_meta = {}
        now = timezone.now()
        has_preference = bool(explicit_weights or behavior_weights)
        exploration_boost = 4.8 if payload["mode"] == "guess" else 3.2

        for artwork in artworks:
            key = str(artwork.id)
            text = self._artwork_text(artwork)
            tags = self._artwork_tags(artwork)
            tag_set = set(tags)
            score = 0.0
            matches = set()

            for tag, weight in explicit_weights.items():
                if tag in tag_set:
                    score += 16 * weight
                    matches.add(tag)
                elif tag and tag in text:
                    score += 5 * weight
                    matches.add(tag)

            for tag, weight in behavior_weights.items():
                if tag in tag_set:
                    score += 5 * math.log1p(weight)
                    matches.add(tag)
                elif tag and tag in text:
                    score += 1.5 * math.log1p(weight)
                    matches.add(tag)

            for tag, weight in negative_weights.items():
                if tag in tag_set:
                    score -= 7 * math.log1p(weight)
                elif tag and tag in text:
                    score -= 2 * math.log1p(weight)

            views = payload["views"].get(key, 0)
            likes = payload["likes"].get(key, 0)
            favorites = payload["favorites"].get(key, 0)
            impressions = payload["impressions"].get(key, 0)
            dwell = payload["dwell"].get(key, 0)
            score += math.log1p(views) * 0.7
            score += math.log1p(likes) * 2.2
            score += math.log1p(favorites) * 3.0
            score += math.log1p(payload["comments"].get(key, 0)) * 1.4
            score += min(math.log1p(dwell) * 0.65, 3.8)
            score += math.log1p(getattr(artwork, "reviews_total", 0) or 0) * 1.2
            if impressions > 1 and not (likes or favorites):
                score -= math.log1p(impressions - 1) * 1.35
            if views > 3 and not (likes or favorites):
                score -= math.log1p(views - 2) * 0.9
            if key in payload["dislikes"]:
                score -= 1000

            age_days = 365.0
            if artwork.created_at:
                age_days = max(0, (now - artwork.created_at).total_seconds() / 86400)
                score += 5.5 * math.exp(-age_days / 28)

            explore_value = self._stable_unit_interval(payload["seed"], payload["mode"], key)
            is_exploration = not matches and explore_value > 0.72
            score += explore_value * exploration_boost
            if not has_preference:
                score += explore_value * 2.2

            scores[key] = score
            matched_tags[key] = matches
            if matches:
                reason = f"因为你喜欢 {' · '.join(sorted(matches)[:2])}"
            elif age_days <= 14:
                reason = "近期新作"
            elif getattr(artwork, "reviews_total", 0):
                reason = "大家正在关注"
            elif is_exploration:
                reason = "探索一种新风格"
            else:
                reason = "为你精选"
            recommendation_meta[key] = {
                "recommendation_reason": reason,
                "is_exploration": is_exploration,
            }

        return scores, matched_tags, recommendation_meta

    def _diversity_rerank(self, artworks, scores):
        """Keep relevance while preventing one author or category dominating the feed."""
        remaining = sorted(
            artworks,
            key=lambda artwork: (
                scores.get(str(artwork.id), 0),
                artwork.created_at.timestamp() if artwork.created_at else 0,
                artwork.id,
            ),
            reverse=True,
        )
        selected = []
        owner_counts = {}
        category_counts = {}
        recent_tags = []
        while remaining:
            best_index = 0
            best_value = float("-inf")
            for index, artwork in enumerate(remaining):
                owner = str(artwork.owner_id)
                category = (artwork.category or "").strip().lower()
                overlap = len(set(self._artwork_tags(artwork)).intersection(recent_tags[-6:]))
                penalty = owner_counts.get(owner, 0) * 1.8
                penalty += category_counts.get(category, 0) * 1.25 if category else 0
                penalty += overlap * 0.7
                value = scores.get(str(artwork.id), 0) - penalty
                if value > best_value:
                    best_value = value
                    best_index = index
            artwork = remaining.pop(best_index)
            selected.append(artwork)
            owner = str(artwork.owner_id)
            category = (artwork.category or "").strip().lower()
            owner_counts[owner] = owner_counts.get(owner, 0) + 1
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            recent_tags.extend(self._artwork_tags(artwork))
        return selected

    def _stable_unit_interval(self, *parts):
        digest = hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / float(2**64 - 1)

    def _add_behavior_weight(self, artwork, weight, behavior_weights):
        if not artwork or weight <= 0:
            return
        for tag in self._artwork_tags(artwork):
            behavior_weights[tag] = behavior_weights.get(tag, 0) + weight
