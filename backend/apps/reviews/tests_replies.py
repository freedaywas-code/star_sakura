from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork


class ReviewReplyTests(APITestCase):
    def setUp(self):
        users = get_user_model()
        self.artist = users.objects.create_user(username="artist", password="test-pass-123")
        self.commenter = users.objects.create_user(username="commenter", password="test-pass-123")
        self.replier = users.objects.create_user(username="replier", password="test-pass-123")
        self.artwork = Artwork.objects.create(owner=self.artist, title="月下花园")
        self.other_artwork = Artwork.objects.create(owner=self.artist, title="海边日落")

    def create_review(self, user, artwork=None, **extra):
        self.client.force_authenticate(user)
        payload = {
            "artwork": (artwork or self.artwork).id,
            "rating": 5,
            "content": "很喜欢这个配色",
            **extra,
        }
        return self.client.post("/api/reviews/", payload, format="json")

    def test_reply_targets_parent_reviewer_and_is_returned_in_list(self):
        root_response = self.create_review(self.commenter)
        self.assertEqual(root_response.status_code, 201)
        root_id = root_response.data["data"]["id"]

        reply_response = self.create_review(
            self.replier,
            parent=root_id,
            content="我也很喜欢光影处理",
        )

        self.assertEqual(reply_response.status_code, 201)
        reply = reply_response.data["data"]
        self.assertEqual(reply["parent"], root_id)
        self.assertEqual(reply["parent_reviewer_username"], "commenter")
        self.assertEqual(reply["target_username"], "commenter")

        list_response = self.client.get(f"/api/reviews/?artwork={self.artwork.id}&page_size=100")
        self.assertEqual(list_response.status_code, 200)
        results = list_response.data["data"]["results"]
        self.assertEqual(len(results), 2)
        self.assertIn(root_id, {item["parent"] for item in results if item["parent"]})

    def test_reply_cannot_point_to_review_from_another_artwork(self):
        root_id = self.create_review(self.commenter).data["data"]["id"]

        response = self.create_review(self.replier, artwork=self.other_artwork, parent=root_id)

        self.assertEqual(response.status_code, 400)

    def test_replies_are_limited_to_two_levels(self):
        root_id = self.create_review(self.commenter).data["data"]["id"]
        reply_id = self.create_review(self.replier, parent=root_id).data["data"]["id"]

        response = self.create_review(self.artist, parent=reply_id)

        self.assertEqual(response.status_code, 400)
