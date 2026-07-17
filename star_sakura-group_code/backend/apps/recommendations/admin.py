from django.contrib import admin

from .models import AIChatMessage, UserAISettings


@admin.register(AIChatMessage)
class AIChatMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "conversation_id", "is_user", "response_mode", "created_at")
    list_filter = ("is_user", "response_mode")
    search_fields = ("user__username", "conversation_id", "message")
    readonly_fields = ("created_at",)


@admin.register(UserAISettings)
class UserAISettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "mode", "custom_model", "has_saved_api_key", "updated_at")
    list_filter = ("mode",)
    search_fields = ("user__username", "custom_model", "custom_api_base")
    readonly_fields = ("created_at", "updated_at", "has_saved_api_key")
    exclude = ("encrypted_api_key",)

    @admin.display(boolean=True, description="已保存 API Key")
    def has_saved_api_key(self, obj):
        return obj.has_api_key
