from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from .models import DirectMessage, Follow


User = get_user_model()


class SocialAPITests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="test-pass-123",
            bio="Alice bio",
            profile={
                "displayName": "Alice Artist",
                "avatar": "",
                "intro": "Public intro",
                "philosophy": "Draw every day",
                "skills": ["watercolor"],
                "creativeYears": "5",
                "birthday": "2000-01-01",
                "gender": "private",
                "homeTags": ["private-tag"],
            },
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="test-pass-123",
        )
        self.carol = User.objects.create_user(
            username="carol",
            email="carol@example.com",
            password="test-pass-123",
        )
        self.inactive = User.objects.create_user(
            username="inactive",
            password="test-pass-123",
            is_active=False,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    @staticmethod
    def profile_url(user):
        return f"/api/users/profiles/{user.username}/"

    @staticmethod
    def follow_url(user):
        return f"/api/users/profiles/{user.username}/follow/"

    @staticmethod
    def messages_url(user):
        return f"/api/users/messages/{user.username}/"

    def send(self, sender, recipient, body):
        self.auth(sender)
        return self.client.post(self.messages_url(recipient), {"body": body}, format="json")

    def follow(self, follower, target):
        self.auth(follower)
        return self.client.post(self.follow_url(target), {}, format="json")

    def test_public_profile_uses_privacy_allowlist_and_supports_username_or_id(self):
        expected_fields = {
            "id",
            "username",
            "display_name",
            "avatar",
            "bio",
            "intro",
            "philosophy",
            "skills",
            "creativeYears",
            "artwork_count",
            "follower_count",
            "following_count",
            "is_following",
            "is_followed_by",
            "is_mutual",
        }
        response = self.client.get(self.profile_url(self.alice))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data["data"]), expected_fields)
        self.assertEqual(response.data["data"]["display_name"], "Alice Artist")
        self.assertNotIn("email", response.data["data"])
        self.assertNotIn("profile", response.data["data"])

        by_id = self.client.get(f"/api/users/profiles/{self.alice.pk}/")
        self.assertEqual(by_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_id.data["data"]["username"], "alice")
        self.assertEqual(
            self.client.get(self.profile_url(self.inactive)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_follow_unfollow_lists_uniqueness_and_self_follow_guard(self):
        self.auth(self.alice)
        self.assertEqual(
            self.client.post(self.follow_url(self.alice), {}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        first = self.client.post(self.follow_url(self.bob), {}, format="json")
        duplicate = self.client.post(self.follow_url(self.bob), {}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertEqual(Follow.objects.filter(from_user=self.alice, to_user=self.bob).count(), 1)

        following = self.client.get("/api/users/following/").data["data"]
        self.assertEqual([item["username"] for item in following["results"]], ["bob"])
        self.auth(self.bob)
        followers = self.client.get("/api/users/followers/").data["data"]
        self.assertEqual([item["username"] for item in followers["results"]], ["alice"])

        self.auth(self.alice)
        removed = self.client.delete(self.follow_url(self.bob))
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertFalse(removed.data["data"]["is_following"])

        with self.assertRaises(IntegrityError), transaction.atomic():
            Follow.objects.create(from_user=self.alice, to_user=self.alice)

    def test_inactive_accounts_cannot_be_followed_or_messaged(self):
        self.auth(self.alice)
        self.assertEqual(
            self.client.post(self.follow_url(self.inactive), {}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(
                self.messages_url(self.inactive),
                {"body": "hello"},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_mutual_limit_is_directional_mutual_is_unlimited_and_unfollow_restores_limit(self):
        self.assertEqual(self.follow(self.alice, self.bob).status_code, status.HTTP_201_CREATED)

        for index, remaining in enumerate([2, 1, 0], start=1):
            response = self.send(self.alice, self.bob, f"alice-{index}")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertFalse(response.data["data"]["unlimited"])
            self.assertEqual(response.data["data"]["remaining_messages"], remaining)
        blocked = self.send(self.alice, self.bob, "alice-4")
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.data["data"]["remaining_messages"], 0)
        self.assertEqual(blocked.data["data"]["message_limit"], 3)

        # A one-way follow does not remove the independent reply-direction limit.
        for index in range(1, 4):
            self.assertEqual(
                self.send(self.bob, self.alice, f"bob-{index}").status_code,
                status.HTTP_201_CREATED,
            )
        self.assertEqual(
            self.send(self.bob, self.alice, "bob-4").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(self.follow(self.bob, self.alice).status_code, status.HTTP_201_CREATED)
        for index in range(4, 8):
            response = self.send(self.alice, self.bob, f"alice-{index}")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertTrue(response.data["data"]["unlimited"])
            self.assertIsNone(response.data["data"]["remaining_messages"])

        self.auth(self.bob)
        self.assertEqual(self.client.delete(self.follow_url(self.alice)).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.send(self.alice, self.bob, "after-unfollow").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            DirectMessage.objects.filter(sender=self.alice, recipient=self.bob).count(),
            7,
        )

    def test_conversation_history_is_private_latest_first_page_and_mark_read(self):
        self.follow(self.alice, self.bob)
        self.follow(self.bob, self.alice)
        for index in range(1, 5):
            self.assertEqual(
                self.send(self.bob, self.alice, f"message-{index}").status_code,
                status.HTTP_201_CREATED,
            )

        self.auth(self.alice)
        conversations = self.client.get("/api/users/messages/conversations/").data["data"]
        self.assertEqual(conversations["total_unread_count"], 4)
        self.assertEqual(conversations["results"][0]["unread_count"], 4)
        self.assertEqual(conversations["results"][0]["last_message"]["body"], "message-4")
        self.assertEqual(
            conversations["results"][0]["last_message_at"],
            conversations["results"][0]["last_message"]["created_at"],
        )

        history = self.client.get(self.messages_url(self.bob) + "?page_size=2").data["data"]
        self.assertEqual(history["messages"]["count"], 4)
        self.assertEqual(
            [message["body"] for message in history["messages"]["results"]],
            ["message-3", "message-4"],
        )
        self.assertTrue(history["unlimited"])

        self.auth(self.carol)
        private_history = self.client.get(self.messages_url(self.bob)).data["data"]
        self.assertEqual(private_history["messages"]["results"], [])

        self.auth(self.alice)
        read = self.client.post(f"/api/users/messages/{self.bob.username}/read/", {}, format="json")
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.assertEqual(read.data["data"]["read_count"], 4)
        self.assertFalse(
            DirectMessage.objects.filter(recipient=self.alice, read_at__isnull=True).exists()
        )

    def test_message_body_validation(self):
        self.auth(self.alice)
        self.assertEqual(
            self.client.post(self.messages_url(self.bob), {"body": "   "}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(
                self.messages_url(self.bob),
                {"body": "x" * (DirectMessage.MAX_BODY_LENGTH + 1)},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

