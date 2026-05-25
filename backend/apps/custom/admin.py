from django.contrib import admin

from .models import CommissionOption, CustomRequest


@admin.register(CustomRequest)
class CustomRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "type_label", "requester", "artist", "budget_note", "status", "progress", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]


@admin.register(CommissionOption)
class CommissionOptionAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "title", "price_label", "sort_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "title", "price_label"]
