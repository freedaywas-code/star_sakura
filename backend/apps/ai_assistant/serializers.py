from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=8000, trim_whitespace=True)


class AIChatSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000, trim_whitespace=True)
    history = ChatMessageSerializer(many=True, required=False, default=list)
    api_key = serializers.CharField(max_length=500, required=False, allow_blank=True, trim_whitespace=True)
    api_base = serializers.URLField(max_length=500, required=False, allow_blank=True)
    model = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    vision_model = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    image_data = serializers.CharField(max_length=4_300_000, required=False, allow_blank=True, trim_whitespace=False)

    def validate_history(self, value):
        return value[-12:]

    def validate_image_data(self, value):
        if not value:
            return ""
        if not value.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
            raise serializers.ValidationError("仅支持 JPG、PNG 或 WebP 图片。")
        return value
