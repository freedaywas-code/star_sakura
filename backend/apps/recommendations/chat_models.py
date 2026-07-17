from django.conf import settings
from django.db import models


class ChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages", verbose_name="用户")
    message = models.TextField("消息内容")
    is_user = models.BooleanField("是否用户消息", default=True)
    is_streaming = models.BooleanField("是否流式响应中", default=False)
    conversation_id = models.CharField("会话ID", max_length=64, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "聊天消息"
        verbose_name_plural = "聊天消息"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} - {'user' if self.is_user else 'ai'} - {self.message[:30]}"