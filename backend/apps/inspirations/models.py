from django.conf import settings
from django.db import models


class Inspiration(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inspirations")
    title = models.CharField(max_length=120)
    tag = models.CharField(max_length=80, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["tag", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title


class InspirationComment(models.Model):
    inspiration = models.ForeignKey(Inspiration, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, related_name="replies", blank=True, null=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inspiration_comments")
    content = models.TextField()
    like_count = models.PositiveIntegerField(default=0)
    liked_by = models.JSONField(default=list, blank=True)
    liked_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="liked_inspiration_comments", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["inspiration", "parent", "created_at"]),
            models.Index(fields=["reviewer", "-created_at"]),
            models.Index(fields=["parent", "created_at"]),
        ]

    def __str__(self):
        return f"{self.reviewer} on {self.inspiration}"
