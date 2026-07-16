import math
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.artworks.models import Artwork
from apps.reviews.models import Review
from apps.users.models import User

from .models import UserAction, UserProfile


ACTION_SCORES = {
    "view": 1.0,
    "like": 5.0,
    "collect": 8.0,
    "comment": 6.0,
    "purchase": 15.0,
    "search": 0.5,
}


def get_action_score(action_type):
    return ACTION_SCORES.get(action_type, 1.0)


def build_user_profile(user, days=30):
    cutoff_date = timezone.now() - timedelta(days=days)
    actions = UserAction.objects.filter(user=user, created_at__gte=cutoff_date)

    category_scores = defaultdict(float)
    tag_scores = defaultdict(float)
    price_bins = defaultdict(int)

    for action in actions:
        score = action.score
        if action.artwork:
            if action.artwork.category:
                category_scores[action.artwork.category] += score
            for tag in action.artwork.tags:
                tag_scores[tag] += score
            price = float(action.artwork.price)
            if price <= 50:
                price_bins["low"] += 1
            elif price <= 200:
                price_bins["medium"] += 1
            else:
                price_bins["high"] += 1
        for tag in action.tags:
            tag_scores[tag] += score * 0.3

    top_categories = sorted(category_scores.items(), key=lambda x: -x[1])[:5]
    top_tags = sorted(tag_scores.items(), key=lambda x: -x[1])[:10]

    preferences = {
        "categories": {cat: score for cat, score in top_categories},
        "tags": {tag: score for tag, score in top_tags},
        "price_bins": dict(price_bins),
    }

    profile, _ = UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "preferences": preferences,
            "top_categories": [cat for cat, _ in top_categories],
            "top_tags": [tag for tag, _ in top_tags],
            "price_range": dict(price_bins),
        },
    )

    return profile


def calculate_artwork_match_score(artwork, profile, weight_category=0.3, weight_tags=0.5, weight_price=0.2):
    score = 0.0
    max_score = 0.0

    if artwork.category and artwork.category in profile.preferences.get("categories", {}):
        score += profile.preferences["categories"][artwork.category] * weight_category
        max_score += max(profile.preferences["categories"].values(), default=1) * weight_category

    tag_prefs = profile.preferences.get("tags", {})
    if tag_prefs:
        matched_tags = [tag for tag in artwork.tags if tag in tag_prefs]
        if matched_tags:
            tag_score = sum(tag_prefs[tag] for tag in matched_tags) / len(artwork.tags)
            score += tag_score * weight_tags
            max_score += max(tag_prefs.values()) * weight_tags

    price = float(artwork.price)
    price_bins = profile.preferences.get("price_bins", {})
    if price_bins:
        if price <= 50:
            bin_key = "low"
        elif price <= 200:
            bin_key = "medium"
        else:
            bin_key = "high"
        if bin_key in price_bins:
            score += price_bins[bin_key] * weight_price
            max_score += max(price_bins.values()) * weight_price

    if max_score == 0:
        return 0.0
    return min(score / max_score, 1.0)


def recommend_artworks_by_profile(user, limit=10, exclude_owned=True):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.preferences.get("categories") and not profile.preferences.get("tags"):
        return recommend_artworks_popular(limit, user)

    artworks = Artwork.objects.filter(is_available=True)
    scored_artworks = []
    
    for artwork in artworks:
        if exclude_owned and artwork.owner_id == user.id:
            continue
        score = calculate_artwork_match_score(artwork, profile)
        if score > 0:
            scored_artworks.append((artwork, score))

    scored_artworks.sort(key=lambda x: -x[1])
    
    if not scored_artworks and exclude_owned:
        for artwork in artworks:
            score = calculate_artwork_match_score(artwork, profile)
            if score > 0:
                scored_artworks.append((artwork, score))
        scored_artworks.sort(key=lambda x: -x[1])

    return [(artwork, score) for artwork, score in scored_artworks[:limit]]


def recommend_artworks_popular(limit=10, user=None):
    recent_date = timezone.now() - timedelta(days=7)
    all_artworks = (
        Artwork.objects
        .filter(is_available=True)
        .annotate(
            view_count=Count("actions", filter=Q(actions__action_type="view", actions__created_at__gte=recent_date)),
            like_count=Count("actions", filter=Q(actions__action_type="like")),
            order_count=Count("orders", filter=Q(orders__status="finished")),
        )
    )

    artworks = all_artworks
    if user:
        artworks = artworks.exclude(owner=user)

    scored = []
    for artwork in artworks:
        score = artwork.view_count * 1 + artwork.like_count * 3 + artwork.order_count * 5
        scored.append((artwork, score))

    scored.sort(key=lambda x: -x[1])
    
    if not scored and user:
        for artwork in all_artworks:
            score = artwork.view_count * 1 + artwork.like_count * 3 + artwork.order_count * 5
            scored.append((artwork, score))
        scored.sort(key=lambda x: -x[1])

    return [(artwork, score / max(scored[0][1], 1) if scored else 0) for artwork, score in scored[:limit]]


def find_similar_users(user, limit=5):
    user_actions = UserAction.objects.filter(user=user)
    user_artwork_ids = set(user_actions.filter(artwork__isnull=False).values_list("artwork_id", flat=True))

    if not user_artwork_ids:
        return []

    similar_users = []
    other_users = User.objects.exclude(id=user.id).annotate(
        action_count=Count("actions"),
    ).filter(action_count__gt=0)

    for other in other_users:
        other_actions = UserAction.objects.filter(user=other)
        other_artwork_ids = set(other_actions.filter(artwork__isnull=False).values_list("artwork_id", flat=True))

        if not other_artwork_ids:
            continue

        intersection = user_artwork_ids & other_artwork_ids
        union = user_artwork_ids | other_artwork_ids

        if len(union) == 0:
            continue

        similarity = len(intersection) / len(union)
        if similarity > 0.1:
            similar_users.append((other, similarity))

    similar_users.sort(key=lambda x: -x[1])
    return similar_users[:limit]


def recommend_artworks_collaborative(user, limit=10):
    similar_users = find_similar_users(user)
    if not similar_users:
        return recommend_artworks_popular(limit, user)

    user_owned_ids = set(Artwork.objects.filter(owner=user).values_list("id", flat=True))
    user_action_ids = set(UserAction.objects.filter(user=user, artwork__isnull=False).values_list("artwork_id", flat=True))

    recommended_scores = defaultdict(float)

    for similar_user, similarity in similar_users:
        similar_actions = UserAction.objects.filter(
            user=similar_user,
            action_type__in=["like", "collect", "purchase"],
        )
        for action in similar_actions:
            if action.artwork_id not in user_owned_ids and action.artwork_id not in user_action_ids:
                recommended_scores[action.artwork_id] += action.score * similarity

    scored_artworks = []
    for artwork_id, score in recommended_scores.items():
        try:
            artwork = Artwork.objects.get(id=artwork_id, is_available=True)
            scored_artworks.append((artwork, score))
        except Artwork.DoesNotExist:
            continue

    scored_artworks.sort(key=lambda x: -x[1])
    max_score = max([s for _, s in scored_artworks], default=1)
    return [(artwork, score / max_score) for artwork, score in scored_artworks[:limit]]


def recommend_artworks_hybrid(user, limit=10, weights=(0.4, 0.3, 0.3)):
    profile_recs = recommend_artworks_by_profile(user, limit * 2)
    collab_recs = recommend_artworks_collaborative(user, limit * 2)
    popular_recs = recommend_artworks_popular(limit * 2, user)

    scores = defaultdict(float)
    artwork_map = {}

    for artwork, score in profile_recs:
        scores[artwork.id] += score * weights[0]
        artwork_map[artwork.id] = artwork

    for artwork, score in collab_recs:
        scores[artwork.id] += score * weights[1]
        artwork_map[artwork.id] = artwork

    for artwork, score in popular_recs:
        scores[artwork.id] += score * weights[2]
        artwork_map[artwork.id] = artwork

    scored = sorted(scores.items(), key=lambda x: -x[1])
    return [(artwork_map[artwork_id], score) for artwork_id, score in scored[:limit]]


def recommend_artists(user, limit=5):
    profile, _ = UserProfile.objects.get_or_create(user=user)

    all_artists = (
        User.objects
        .exclude(id=user.id)
        .annotate(artwork_count=Count("artworks"))
        .filter(artwork_count__gt=0)
    )

    scored_artists = []
    for artist in all_artists:
        artist_artworks = Artwork.objects.filter(owner=artist)
        avg_match = 0.0
        count = 0
        for artwork in artist_artworks[:10]:
            avg_match += calculate_artwork_match_score(artwork, profile)
            count += 1

        if count > 0:
            match_score = avg_match / count
        else:
            match_score = 0.0

        reviews = Review.objects.filter(target_user=artist)
        avg_rating = reviews.aggregate(Avg("rating"))["rating__avg"] or 0

        top_categories = list(
            artist_artworks
            .values("category")
            .annotate(count=Count("category"))
            .order_by("-count")[:3]
            .values_list("category", flat=True)
        )

        final_score = match_score * 0.6 + (avg_rating / 5) * 0.3 + (artist.artwork_count / 100) * 0.1
        scored_artists.append((artist, final_score, artist.artwork_count, avg_rating, top_categories))

    scored_artists.sort(key=lambda x: -x[1])
    return [
        {
            "artist": artist,
            "match_score": score,
            "artwork_count": artwork_count,
            "avg_rating": avg_rating,
            "top_categories": top_categories,
        }
        for artist, score, artwork_count, avg_rating, top_categories in scored_artists[:limit]
    ]


def log_action(user, action_type, artwork=None, tags=None):
    score = get_action_score(action_type)
    UserAction.objects.create(
        user=user,
        artwork=artwork,
        action_type=action_type,
        tags=tags or [],
        score=score,
    )
    build_user_profile(user)