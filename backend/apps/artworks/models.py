from django.conf import settings
from django.db import models


class Artwork(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="artworks", verbose_name="作者")
    title = models.CharField("标题", max_length=120)
    description = models.TextField("描述", blank=True)
    image = models.ImageField("画作图片", upload_to="artworks/%Y/%m/", blank=True, null=True)
    category = models.CharField("分类", max_length=50, blank=True)
    tags = models.JSONField("标签", default=list, blank=True)
    price = models.DecimalField("价格", max_digits=10, decimal_places=2, default=0)
    is_available = models.BooleanField("可购买", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "画作"
        verbose_name_plural = "画作"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
