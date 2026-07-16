from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["id", "artwork", "reviewer", "target_user", "rating", "like_count", "created_at"]
    list_filter = ["rating", "created_at"]
    search_fields = ["content", "artwork__title", "reviewer__username", "target_user__username"]
