from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "artwork", "buyer", "seller", "quantity", "total_price", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["artwork__title", "buyer__username", "seller__username"]
