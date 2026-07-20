from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.artworks.models import Artwork
from apps.reviews.models import Review

from .models import DirectMessage


class MessageReviewCompatibilityTests(APITestCase):
    def setUp(self):
        users = get_user_model()
        self.artist = users.objects.create_user(username="compat-artist", password="test-pass-123")
        self.commenter = users.objects.create_user(username="compat-commenter", password="test-pass-123")
        self.replier = users.objects.create_user(username="compat-replier", password="test-pass-123")
        self.artwork = Artwork.objects.create(owner=self.artist, title="兼容性测试作品")

    def test_comment_replies_do_not_change_direct_message_history(self):
        message = DirectMessage.objects.create(
            sender=self.commenter,
            recipient=self.artist,
            body="这是一条独立的私信",
        )
        root = Review.objects.create(
            artwork=self.artwork,
            reviewer=self.commenter,
            target_user=self.artist,
            rating=5,
            content="作品评论",
        )
        Review.objects.create(
            artwork=self.artwork,
            parent=root,
            reviewer=self.replier,
            target_user=self.commenter,
            rating=5,
            content="评论回复",
        )

        self.client.force_authenticate(self.artist)
        conversations = self.client.get("/api/users/messages/conversations/?page_size=100")
        history = self.client.get(f"/api/users/messages/{self.commenter.username}/?page_size=50")

        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(conversations.data["data"]["count"], 1)
        self.assertEqual(
            [item["id"] for item in history.data["data"]["messages"]["results"]],
            [message.id],
        )
        self.assertEqual(self.commenter.sent_direct_messages.count(), 1)
        self.assertEqual(self.commenter.given_reviews.count(), 1)
        self.assertEqual(self.commenter.received_reviews.count(), 1)
