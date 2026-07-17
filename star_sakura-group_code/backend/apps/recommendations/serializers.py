from rest_framework import serializers
from django.views.decorators.debug import sensitive_variables

from .ai import AIServiceError, normalized_api_origin, validate_custom_api_base
from .models import UserAISettings


class ChatSendSerializer(serializers.Serializer):
    content = serializers.CharField(
        trim_whitespace=True,
        allow_blank=False,
        max_length=10000,
    )
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class ChatHistoryQuerySerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(required=False, default=50, min_value=1, max_value=100)


class ConversationQuerySerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=True)


class AISettingsUpdateSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=UserAISettings.Mode.choices)
    api_base = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )
    model = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    api_key = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        max_length=4096,
        write_only=True,
    )

    @sensitive_variables()
    def validate(self, attrs):
        if attrs["mode"] != UserAISettings.Mode.CUSTOM:
            return attrs

        api_base = str(attrs.get("api_base") or "").strip()
        model = str(attrs.get("model") or "").strip()
        api_key = str(attrs.get("api_key") or "")
        errors = {}
        if not api_base:
            errors["api_base"] = "自定义模式必须填写 API 地址"
        else:
            try:
                api_base = validate_custom_api_base(api_base, resolve_dns=True)
            except AIServiceError as exc:
                errors["api_base"] = str(exc)
        if not model:
            errors["model"] = "自定义模式必须填写模型名称"
        elif any(ord(character) < 32 for character in model):
            errors["model"] = "模型名称格式无效"
        current = self.context.get("current_settings")
        if not api_key:
            if not (current and current.has_api_key):
                errors["api_key"] = "首次使用自定义模型必须填写 API Key"
            else:
                try:
                    old_origin = normalized_api_origin(current.custom_api_base)
                    new_origin = normalized_api_origin(api_base)
                except AIServiceError:
                    old_origin = None
                    new_origin = None
                if not old_origin or old_origin != new_origin:
                    errors["api_key"] = "更换 API 服务商地址时必须重新填写 API Key"
        elif any(not 0x21 <= ord(character) <= 0x7E for character in api_key):
            errors["api_key"] = "API Key 必须仅包含可打印 ASCII 字符"
        if errors:
            raise serializers.ValidationError(errors)
        attrs["api_base"] = api_base
        attrs["model"] = model
        attrs["api_key"] = api_key
        return attrs
