from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CustomRequest(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "待接单"
        ACCEPTED = "accepted", "已接单"
        ABANDON_REQUESTED = "abandon_requested", "申请放弃中"
        IN_PROGRESS = "in_progress", "创作中"
        REVIEWING = "reviewing", "待确认"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="custom_requests",
        verbose_name="需求方",
    )
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="custom_jobs",
        verbose_name="接单画师",
        blank=True,
        null=True,
    )
    title = models.CharField("定制标题", max_length=120)
    type_label = models.CharField("委托类型", max_length=80, blank=True)
    description = models.TextField("需求描述")
    reference_image = models.ImageField("参考图", upload_to="custom/%Y/%m/", blank=True, null=True)
    budget = models.DecimalField("预算数值", max_digits=10, decimal_places=2, default=0)
    budget_note = models.CharField("预算说明", max_length=80, blank=True)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    progress = models.PositiveSmallIntegerField("进度", default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    accepted_at = models.DateTimeField("接单时间", blank=True, null=True)
    abandon_requested_at = models.DateTimeField("申请放弃时间", blank=True, null=True)
    agreed_price = models.DecimalField(
        "成交价",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    selected_bid = models.OneToOneField(
        "CommissionBid",
        on_delete=models.SET_NULL,
        related_name="selected_for_request",
        verbose_name="中选报价",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "线上定制"
        verbose_name_plural = "线上定制"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["requester", "-created_at"]),
            models.Index(fields=["artist", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title


class CommissionBid(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "竞价中"
        WITHDRAWN = "withdrawn", "已撤回"
        SELECTED = "selected", "已中选"
        REJECTED = "rejected", "未中选"

    custom_request = models.ForeignKey(
        CustomRequest,
        on_delete=models.CASCADE,
        related_name="bids",
        verbose_name="委托",
    )
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commission_bids",
        verbose_name="报价画师",
    )
    amount = models.DecimalField(
        "报价",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    message = models.TextField("报价说明", max_length=1000, blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "委托报价"
        verbose_name_plural = "委托报价"
        ordering = ["amount", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["custom_request", "artist"],
                name="custom_unique_bid_artist",
            ),
            models.UniqueConstraint(
                fields=["custom_request"],
                condition=models.Q(status="selected"),
                name="custom_one_selected_bid",
            ),
        ]
        indexes = [
            models.Index(fields=["custom_request", "status", "-updated_at"]),
            models.Index(fields=["artist", "status", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.custom_request} - {self.artist}: {self.amount}"


class CommissionInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待回应"
        ACCEPTED = "accepted", "已接受"
        DECLINED = "declined", "已拒绝"
        CANCELLED = "cancelled", "已取消"

    custom_request = models.ForeignKey(
        CustomRequest,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name="委托",
    )
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_commission_invitations",
        verbose_name="受邀画师",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_commission_invitations",
        verbose_name="邀请人",
    )
    amount = models.DecimalField(
        "邀请报价",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    message = models.TextField("邀请说明", max_length=1000, blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.PENDING)
    responded_at = models.DateTimeField("回应时间", blank=True, null=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "定向邀请"
        verbose_name_plural = "定向邀请"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["custom_request", "artist"],
                name="custom_unique_invite_artist",
            ),
            models.CheckConstraint(
                condition=~models.Q(artist=models.F("invited_by")),
                name="custom_inviter_not_artist",
            ),
        ]
        indexes = [
            models.Index(fields=["custom_request", "status", "-updated_at"]),
            models.Index(fields=["artist", "status", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.custom_request} -> {self.artist}"


class CommissionOption(models.Model):
    code = models.SlugField("选项代码", max_length=40, unique=True)
    title = models.CharField("委托类型", max_length=80)
    price_label = models.CharField("价格说明", max_length=80, blank=True)
    sort_order = models.PositiveSmallIntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "委托类型"
        verbose_name_plural = "委托类型"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.title
