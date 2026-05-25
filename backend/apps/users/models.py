from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    is_admin = models.BooleanField("平台管理员", default=False)
    avatar = models.ImageField("头像", upload_to="avatars/", blank=True, null=True)
    bio = models.TextField("简介", blank=True)

    profile = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def save(self, *args, **kwargs):
        if self.is_admin:
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
