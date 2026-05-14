from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CustomRequest(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已提交"
        ACCEPTED = "accepted", "已接单"
        IN_PROGRESS = "in_progress", "创作中"
        REVIEWING = "reviewing", "待确认"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="custom_requests", verbose_name="需求方")
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="custom_jobs",
        verbose_name="接单画师",
        blank=True,
        null=True,
    )
    title = models.CharField("定制标题", max_length=120)
    description = models.TextField("需求描述")
    reference_image = models.ImageField("参考图", upload_to="custom/%Y/%m/", blank=True, null=True)
    budget = models.DecimalField("预算", max_digits=10, decimal_places=2, default=0)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    progress = models.PositiveSmallIntegerField("进度", default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "线上定制"
        verbose_name_plural = "线上定制"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
