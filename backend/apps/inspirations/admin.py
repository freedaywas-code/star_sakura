from django.contrib import admin

from .models import Inspiration


@admin.register(Inspiration)
class InspirationAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "tag", "created_at")
    list_filter = ("tag", "created_at")
    search_fields = ("title", "tag", "content", "owner__username")
    autocomplete_fields = ("owner",)
