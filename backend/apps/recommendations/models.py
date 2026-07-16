from django.conf import settings
from django.db import models


class UserAction(models.Model):
    class ActionType(models.TextChoices):
        VIEW = "view", "浏览"
        LIKE = "like", "点赞"
        PURCHASE = "purchase", "购买"
        COLLECT = "collect", "收藏"
        COMMENT = "comment", "评论"
        SEARCH = "search", "搜索"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="actions", verbose_name="用户")
    artwork = models.ForeignKey("artworks.Artwork", on_delete=models.CASCADE, related_name="actions", blank=True, null=True, verbose_name="画作")
    action_type = models.CharField("行为类型", max_length=20, choices=ActionType.choices)
    tags = models.JSONField("搜索标签", default=list, blank=True)
    score = models.FloatField("行为得分", default=1.0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "用户行为"
        verbose_name_plural = "用户行为"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["artwork", "-created_at"]),
            models.Index(fields=["action_type", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.artwork}"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommend_profile", verbose_name="用户")
    preferences = models.JSONField("偏好向量", default=dict)
    top_categories = models.JSONField("偏好分类", default=list)
    top_tags = models.JSONField("偏好标签", default=list)
    price_range = models.JSONField("价格区间偏好", default=dict)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "用户推荐画像"
        verbose_name_plural = "用户推荐画像"

    def __str__(self):
        return f"Profile: {self.user}"