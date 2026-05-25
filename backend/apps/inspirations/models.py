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
