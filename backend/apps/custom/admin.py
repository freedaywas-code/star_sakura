from django.contrib import admin

from .models import CustomRequest


@admin.register(CustomRequest)
class CustomRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "requester", "artist", "budget", "status", "progress", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "description", "requester__username", "artist__username"]
