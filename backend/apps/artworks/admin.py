from django.contrib import admin

from .models import Artwork


@admin.register(Artwork)
class ArtworkAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "owner", "category", "price", "is_available", "created_at"]
    list_filter = ["category", "is_available", "created_at"]
    search_fields = ["title", "description", "owner__username"]
