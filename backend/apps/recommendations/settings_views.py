from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from rest_framework import permissions
from rest_framework.viewsets import GenericViewSet

from common.response import ApiResponseMixin, fail, ok

from .ai import AIServiceError, call_ai, get_ai_config, get_ai_selection
from .models import UserAISettings
from .serializers import AISettingsUpdateSerializer


def _current_settings(user):
    return UserAISettings.objects.filter(user=user).first()


def _official_available():
    try:
        get_ai_config(None)
    except AIServiceError:
        return False
    return True


def settings_payload(user):
    current = _current_settings(user)
    return {
        "mode": current.mode if current else UserAISettings.Mode.OFFICIAL,
        "official": {
            "available": _official_available(),
            "model": str(getattr(settings, "AI_MODEL", "") or "") or None,
        },
        "custom": {
            "api_base": current.custom_api_base if current else "",
            "model": current.custom_model if current else "",
            "has_api_key": current.has_api_key if current else False,
        },
    }


class AISettingsViewSet(ApiResponseMixin, GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "ai_settings"

    def retrieve_settings(self, request):
        return ok(settings_payload(request.user))

    @sensitive_variables()
    def update_settings(self, request):
        current = _current_settings(request.user)
        serializer = AISettingsUpdateSerializer(
            data=request.data,
            context={"current_settings": current},
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        api_key = data.pop("api_key", "")
        current = current or UserAISettings(user=request.user)
        if data["mode"] == UserAISettings.Mode.CUSTOM:
            current.custom_api_base = data["api_base"]
            current.custom_model = data["model"]
            if api_key:
                current.set_api_key(api_key)
        current.mode = data["mode"]
        current.save()
        return ok(settings_payload(request.user), message="AI 模型设置已保存")

    def delete_settings(self, request):
        UserAISettings.objects.filter(user=request.user).delete()
        return ok(settings_payload(request.user), message="已恢复为官方模型")


class AISettingsTestViewSet(ApiResponseMixin, GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "ai_settings_test"

    @sensitive_variables()
    def test_connection(self, request):
        selection = get_ai_selection(request.user)
        safe_data = {
            "status": "error",
            "model": selection["model"],
            "provider": selection["provider"],
        }
        try:
            config = get_ai_config(request.user)
            call_ai(
                "这是连接测试。请简短回复 OK。",
                [{"role": "user", "content": "连接测试"}],
                config=config,
            )
        except AIServiceError:
            return fail(
                "模型连接测试失败",
                data=safe_data,
                status=502,
                code=502,
            )
        return ok(
            {
                "status": "success",
                "model": config.model,
                "provider": config.provider,
            },
            message="模型连接测试成功",
        )
