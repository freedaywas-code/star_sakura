from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    is_admin = models.BooleanField("平台管理员", default=False)
    avatar = models.ImageField("头像", upload_to="avatars/", blank=True, null=True)
    bio = models.TextField("简介", blank=True)

    profile = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_admin", "-date_joined"]),
        ]

    def save(self, *args, **kwargs):
        if self.is_admin:
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class Follow(models.Model):
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="following_relations",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="follower_relations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                name="users_follow_unique_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="users_follow_no_self",
            ),
        ]
        indexes = [
            models.Index(fields=["from_user", "-created_at"]),
            models.Index(fields=["to_user", "-created_at"]),
        ]

    def clean(self):
        super().clean()
        if self.from_user_id and self.from_user_id == self.to_user_id:
            raise ValidationError({"to_user": "You cannot follow yourself."})

    def __str__(self):
        return f"{self.from_user} -> {self.to_user}"


class DirectMessage(models.Model):
    MAX_BODY_LENGTH = 2000

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_direct_messages",
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_direct_messages",
    )
    body = models.CharField(max_length=MAX_BODY_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(sender=models.F("recipient")),
                name="users_dm_no_self",
            ),
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="users_dm_body_not_empty",
            ),
        ]
        indexes = [
            models.Index(fields=["sender", "recipient", "created_at"]),
            models.Index(fields=["recipient", "read_at", "-created_at"]),
            models.Index(fields=["sender", "-created_at"]),
        ]

    def clean(self):
        super().clean()
        if self.sender_id and self.sender_id == self.recipient_id:
            raise ValidationError({"recipient": "You cannot send a direct message to yourself."})
        if not (self.body or "").strip():
            raise ValidationError({"body": "Message body cannot be empty."})

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.body[:30]}"
