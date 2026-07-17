import base64
import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.views.decorators.debug import sensitive_variables
from cryptography.fernet import Fernet, InvalidToken


class AICredentialError(Exception):
    """Raised when a stored user credential cannot be decrypted."""


@sensitive_variables()
def _credential_cipher():
    """Build a stable Fernet cipher without ever persisting its source secret."""
    source = (
        getattr(settings, "AI_CREDENTIAL_ENCRYPTION_KEY", "")
        or settings.SECRET_KEY
    )
    raw = str(source).encode("utf-8")
    try:
        # Operators may provide a generated Fernet key directly.
        return Fernet(raw)
    except (TypeError, ValueError):
        # Otherwise derive a valid key from the dedicated secret/SECRET_KEY.
        derived = base64.urlsafe_b64encode(
            hashlib.sha256(b"star-sakura:user-ai-credential:v1:" + raw).digest()
        )
        return Fernet(derived)


class AIChatMessage(models.Model):
    class ResponseMode(models.TextChoices):
        AI = "ai", "AI"
        LOCAL = "local", "本地"
        FALLBACK = "fallback", "降级"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_chat_messages",
        verbose_name="用户",
    )
    message = models.TextField("消息内容")
    is_user = models.BooleanField("是否用户消息", default=True)
    response_mode = models.CharField(
        "回复模式",
        max_length=16,
        choices=ResponseMode.choices,
        blank=True,
        default="",
    )
    turn_data = models.JSONField("结构化轮次数据", default=dict, blank=True)
    conversation_id = models.UUIDField("会话 ID", default=uuid.uuid4)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "AI 聊天消息"
        verbose_name_plural = "AI 聊天消息"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["user", "conversation_id", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        role = "user" if self.is_user else "ai"
        return f"{self.user} - {role} - {self.message[:30]}"


class UserAISettings(models.Model):
    class Mode(models.TextChoices):
        OFFICIAL = "official", "官方模型"
        CUSTOM = "custom", "自定义模型"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_settings",
        verbose_name="用户",
    )
    mode = models.CharField(
        "模型来源",
        max_length=16,
        choices=Mode.choices,
        default=Mode.OFFICIAL,
    )
    custom_api_base = models.URLField("自定义 API 地址", max_length=500, blank=True)
    custom_model = models.CharField("自定义模型", max_length=200, blank=True)
    encrypted_api_key = models.TextField("加密 API 密钥", blank=True, editable=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "用户 AI 设置"
        verbose_name_plural = "用户 AI 设置"

    @property
    def has_api_key(self):
        return bool(self.encrypted_api_key)

    @sensitive_variables()
    def set_api_key(self, value):
        value = str(value or "")
        if not value:
            self.encrypted_api_key = ""
            return
        self.encrypted_api_key = _credential_cipher().encrypt(
            value.encode("utf-8")
        ).decode("ascii")

    @sensitive_variables()
    def get_api_key(self):
        if not self.encrypted_api_key:
            return ""
        try:
            return _credential_cipher().decrypt(
                self.encrypted_api_key.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
            raise AICredentialError("无法读取已保存的 API 密钥") from exc

    def __str__(self):
        return f"{self.user} - {self.get_mode_display()}"
