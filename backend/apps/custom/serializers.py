from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import CustomRequest


class CustomRequestSerializer(serializers.ModelSerializer):
    requester_username = serializers.CharField(source="requester.username", read_only=True)
    artist_username = serializers.CharField(source="artist.username", read_only=True)
    budget = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CustomRequest
        fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "title",
            "type_label",
            "description",
            "reference_image",
            "budget",
            "status",
            "progress",
            "accepted_at",
            "abandon_requested_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requester",
            "requester_username",
            "artist",
            "artist_username",
            "status",
            "progress",
            "accepted_at",
            "abandon_requested_at",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["budget"] = instance.budget_note or str(instance.budget)
        data["status"] = "open" if instance.status == CustomRequest.Status.SUBMITTED else instance.status
        return data

    def _apply_budget(self, validated_data):
        budget_text = str(validated_data.pop("budget", "") or "").strip()
        validated_data["budget_note"] = budget_text
        try:
            validated_data["budget"] = Decimal(budget_text) if budget_text else Decimal("0")
        except (InvalidOperation, ValueError):
            validated_data["budget"] = Decimal("0")
        return validated_data

    def create(self, validated_data):
        return super().create(self._apply_budget(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._apply_budget(validated_data))
