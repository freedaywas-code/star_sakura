from django.contrib import admin

from .models import Inspiration, InspirationComment


@admin.register(Inspiration)
class InspirationAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "tag", "created_at")
    list_filter = ("tag", "created_at")
    search_fields = ("title", "tag", "content", "owner__username")
    autocomplete_fields = ("owner",)


@admin.register(InspirationComment)
class InspirationCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "inspiration", "reviewer", "parent", "like_count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "inspiration__title", "reviewer__username")
    autocomplete_fields = ("inspiration", "parent", "reviewer")
