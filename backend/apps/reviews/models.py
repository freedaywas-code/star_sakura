from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="review", verbose_name="订单", blank=True, null=True)
    artwork = models.ForeignKey("artworks.Artwork", on_delete=models.CASCADE, related_name="reviews", verbose_name="画作")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="given_reviews", verbose_name="评价人")
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_reviews", verbose_name="被评价人")
    rating = models.PositiveSmallIntegerField("评分", validators=[MinValueValidator(1), MaxValueValidator(5)])
    content = models.TextField("评价内容", blank=True)
    image = models.ImageField("评价图片", upload_to="reviews/%Y/%m/", blank=True, null=True)
    like_count = models.PositiveIntegerField("点赞数", default=0)
    liked_by = models.JSONField("点赞用户", default=list, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "评价"
        verbose_name_plural = "评价"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating} 星 - {self.artwork}"
