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

    def test_dislike_and_repeated_exposure_reduce_rank(self):
        results = self.results({
            "tags": ["水彩"],
            "impressions": {str(self.watercolor_seen.id): 50},
            "dislikes": [f"artwork:{self.pixel.id}"],
            "seed": "fatigue-test",
        })
        ids = [item["id"] for item in results]

        self.assertLess(ids.index(self.watercolor_fresh.id), ids.index(self.watercolor_seen.id))
        self.assertEqual(ids[-1], self.pixel.id)

    def test_same_seed_produces_stable_feed(self):
        payload = {"tags": [], "seed": "same-session", "mode": "guess"}
        first = [item["id"] for item in self.results(payload)]
        second = [item["id"] for item in self.results(payload)]

        self.assertEqual(first, second)
