from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import DirectMessage, Follow


User = get_user_model()


class SocialPrivacyAndLimitReviewTests(APITestCase):
    """Regression coverage for the trust boundaries of follows and direct messages."""

    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice-review",
            email="alice-private@example.com",
            password="test-pass-123",
            profile={
                "displayName": "Alice",
                "intro": "Public introduction",
                "skills": ["watercolor"],
                "birthday": "2000-01-02",
                "gender": "private",
                "homeTags": ["private-preference"],
            },
        )
        self.bob = User.objects.create_user(
            username="bob-review",
            email="bob-private@example.com",
            password="test-pass-123",
        )
        self.outsider = User.objects.create_user(
            username="outsider-review",
            password="test-pass-123",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def follow(self, follower, target):
        self.auth(follower)
        return self.client.post(f"/api/users/profiles/{target.username}/follow/", {}, format="json")

    def unfollow(self, follower, target):
        self.auth(follower)
        return self.client.delete(f"/api/users/profiles/{target.username}/follow/")

    def send(self, sender, recipient, body):
        self.auth(sender)
        return self.client.post(
            f"/api/users/messages/{recipient.username}/",
            {"body": body},
            format="json",
        )

    def test_public_profile_uses_an_explicit_privacy_allowlist(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/users/profiles/{self.alice.username}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.data["data"]
        self.assertEqual(profile["username"], self.alice.username)
        self.assertEqual(profile["display_name"], "Alice")
        self.assertEqual(profile["skills"], ["watercolor"])
        for private_field in (
            "email",
            "is_admin",
            "profile",
            "birthday",
            "gender",
            "homeTags",
            "password",
        ):
            self.assertNotIn(private_field, profile)

    def test_three_message_allowance_is_directional_and_only_mutual_follow_is_unlimited(self):
        for index in range(3):
            response = self.send(self.alice, self.bob, f"alice-{index}")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.send(self.alice, self.bob, "alice-blocked").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # The opposite direction has its own allowance.
        for index in range(3):
            response = self.send(self.bob, self.alice, f"bob-{index}")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # A one-way follow is not enough to remove the limit.
        self.assertEqual(self.follow(self.bob, self.alice).status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.send(self.alice, self.bob, "still-blocked").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(self.follow(self.alice, self.bob).status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.send(self.alice, self.bob, "mutual-unlimited").status_code,
            status.HTTP_201_CREATED,
        )

        # Removing either side of the mutual follow restores the historical cap.
        self.assertEqual(self.unfollow(self.alice, self.bob).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.send(self.alice, self.bob, "blocked-again").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            DirectMessage.objects.filter(sender=self.alice, recipient=self.bob).count(),
            4,
        )

    def test_read_updates_and_history_are_always_scoped_to_the_authenticated_user(self):
        message = DirectMessage.objects.create(
            sender=self.alice,
            recipient=self.bob,
            body="private message",
        )

        self.auth(self.outsider)
        history = self.client.get(f"/api/users/messages/{self.bob.username}/")
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data["data"]["messages"]["results"], [])

        response = self.client.post(f"/api/users/messages/{self.alice.username}/read/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["read_count"], 0)
        message.refresh_from_db()
        self.assertIsNone(message.read_at)

        self.auth(self.bob)
        history = self.client.get(f"/api/users/messages/{self.alice.username}/")
        self.assertEqual(
            [item["body"] for item in history.data["data"]["messages"]["results"]],
            ["private message"],
        )
        response = self.client.post(f"/api/users/messages/{self.alice.username}/read/", {}, format="json")
        self.assertEqual(response.data["data"]["read_count"], 1)
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)

    def test_self_relationships_and_anonymous_messaging_are_rejected(self):
        self.auth(self.alice)
        self.assertEqual(
            self.client.post(
                f"/api/users/profiles/{self.alice.username}/follow/",
                {},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(
                f"/api/users/messages/{self.alice.username}/",
                {"body": "self"},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(Follow.objects.filter(from_user=self.alice, to_user=self.alice).exists())

        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.post(
                f"/api/users/messages/{self.bob.username}/",
                {"body": "anonymous"},
                format="json",
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_internal_profile_reload_uses_primary_key_when_a_numeric_username_collides(self):
        target = User.objects.create_user(
            username="numeric-collision-target",
            password="test-pass-123",
        )
        numeric_username_user = User.objects.create_user(
            username=str(target.pk),
            password="test-pass-123",
        )
        self.assertNotEqual(target.pk, numeric_username_user.pk)

        self.auth(self.alice)
        followed = self.client.post(
            f"/api/users/profiles/{target.username}/follow/",
            {},
            format="json",
        )
        self.assertEqual(followed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(followed.data["data"]["id"], target.pk)
        self.assertEqual(followed.data["data"]["username"], target.username)
        self.assertTrue(Follow.objects.filter(from_user=self.alice, to_user=target).exists())

        DirectMessage.objects.create(
            sender=self.alice,
            recipient=target,
            body="message for the intended target",
        )
        history = self.client.get(f"/api/users/messages/{target.username}/")
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data["data"]["user"]["id"], target.pk)
        self.assertEqual(history.data["data"]["user"]["username"], target.username)
        self.assertEqual(
            [item["body"] for item in history.data["data"]["messages"]["results"]],
            ["message for the intended target"],
        )

        unfollowed = self.client.delete(f"/api/users/profiles/{target.username}/follow/")
        self.assertEqual(unfollowed.status_code, status.HTTP_200_OK)
        self.assertEqual(unfollowed.data["data"]["id"], target.pk)
        self.assertEqual(unfollowed.data["data"]["username"], target.username)
        self.assertFalse(Follow.objects.filter(from_user=self.alice, to_user=target).exists())
