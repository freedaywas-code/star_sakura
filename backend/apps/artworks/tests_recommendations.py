from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Artwork


class ArtworkRecommendationTests(APITestCase):
    def setUp(self):
        users = get_user_model()
        self.viewer = users.objects.create_user(
            username="viewer",
            password="test-pass-123",
            profile={"homeTags": ["水彩"]},
        )
        self.artist_a = users.objects.create_user(username="artist-a", password="test-pass-123")
        self.artist_b = users.objects.create_user(username="artist-b", password="test-pass-123")
        self.watercolor_seen = Artwork.objects.create(
            owner=self.artist_a,
            title="水彩花园",
            description="透明水色与植物",
            category="水彩",
            tags=["植物", "清新"],
        )
        self.watercolor_fresh = Artwork.objects.create(
            owner=self.artist_b,
            title="雨后街道",
            description="水彩城市速写",
            category="水彩",
            tags=["城市", "速写"],
        )
        self.pixel = Artwork.objects.create(
            owner=self.artist_a,
            title="像素宇宙",
            description="复古游戏场景",
            category="像素",
            tags=["游戏", "科幻"],
        )

    def results(self, payload):
        response = self.client.post(
            "/api/artworks/recommendations/?page_size=50",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.data["data"]["results"]

    def test_interest_tags_and_metadata_drive_ranking(self):
        results = self.results({"tags": ["水彩"], "seed": "stable-user", "mode": "feed"})

        self.assertIn(results[0]["id"], {self.watercolor_seen.id, self.watercolor_fresh.id})
        self.assertIn("水彩", results[0]["matched_tags"])
        self.assertTrue(results[0]["recommendation_reason"].startswith("因为你喜欢"))
        self.assertIn("is_exploration", results[0])

    def test_dislike_filters_item_and_repeated_exposure_reduces_rank(self):
        results = self.results({
            "tags": ["水彩"],
            "impressions": {str(self.watercolor_seen.id): 50},
            "dislikes": [f"artwork:{self.pixel.id}"],
            "seed": "fatigue-test",
        })
        ids = [item["id"] for item in results]

        self.assertLess(ids.index(self.watercolor_fresh.id), ids.index(self.watercolor_seen.id))
        self.assertNotIn(self.pixel.id, ids)

    def test_dislike_filter_is_applied_before_pagination(self):
        response = self.client.post(
            "/api/artworks/recommendations/?page_size=2",
            {
                "dislikes": [f"artwork:{self.watercolor_seen.id}"],
                "seed": "filtered-page",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(len(data["results"]), 2)
        self.assertNotIn(self.watercolor_seen.id, [item["id"] for item in data["results"]])

    def test_positive_interaction_protects_repeatedly_exposed_item(self):
        payload = {
            "tags": [],
            "impressions": {str(self.watercolor_seen.id): 50},
            "likes": {str(self.watercolor_seen.id): 1},
            "seed": "positive-after-exposure",
        }
        results = self.results(payload)
        seen = next(item for item in results if item["id"] == self.watercolor_seen.id)

        self.assertGreater(seen["recommendation_score"], 0)

    def test_same_seed_produces_stable_feed(self):
        payload = {"tags": [], "seed": "same-session", "mode": "guess"}
        first = self.results(payload)
        second = self.results(payload)

        self.assertEqual(
            [(item["id"], item["recommendation_score"], item["is_exploration"]) for item in first],
            [(item["id"], item["recommendation_score"], item["is_exploration"]) for item in second],
        )

    def test_guess_mode_keeps_personal_relevance_and_exploration_metadata(self):
        results = self.results({"tags": ["水彩"], "seed": "guess-entry", "mode": "guess"})

        self.assertIn(results[0]["id"], {self.watercolor_seen.id, self.watercolor_fresh.id})
        self.assertTrue(all("is_exploration" in item for item in results))
