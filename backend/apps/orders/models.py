from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待接单"
        ACCEPTED = "accepted", "已接单"
        PAID = "paid", "已付款"
        FINISHED = "finished", "已完成"
        CANCELLED = "cancelled", "已取消"

    artwork = models.ForeignKey("artworks.Artwork", on_delete=models.PROTECT, related_name="orders", verbose_name="画作")
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buy_orders", verbose_name="买家")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sell_orders", verbose_name="卖家")
    quantity = models.PositiveIntegerField("数量", default=1)
    total_price = models.DecimalField("总价", max_digits=10, decimal_places=2)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    note = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "订单"
        verbose_name_plural = "订单"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["artwork", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"订单 #{self.id} - {self.artwork}"
