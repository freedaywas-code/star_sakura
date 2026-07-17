from django.contrib import admin

<<<<<<< HEAD
from .models import CommissionOption, CustomRequest
=======
from .models import CommissionBid, CommissionInvitation, CommissionOption, CustomRequest


class CommissionBidInline(admin.TabularInline):
    model = CommissionBid
    extra = 0
    fields = ["artist", "amount", "message", "status", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]


class CommissionInvitationInline(admin.TabularInline):
    model = CommissionInvitation
    extra = 0
    fields = ["artist", "invited_by", "amount", "message", "status", "responded_at"]
>>>>>>> origin/group_code


@admin.register(CustomRequest)
class CustomRequestAdmin(admin.ModelAdmin):
<<<<<<< HEAD
    list_display = ["id", "title", "type_label", "requester", "artist", "budget_note", "status", "progress", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]
=======
    list_display = [
        "id",
        "title",
        "type_label",
        "requester",
        "artist",
        "budget_note",
        "agreed_price",
        "status",
        "progress",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "type_label", "description", "requester__username", "artist__username"]
    readonly_fields = ["selected_bid", "accepted_at", "abandon_requested_at", "created_at", "updated_at"]
    inlines = [CommissionBidInline, CommissionInvitationInline]


@admin.register(CommissionBid)
class CommissionBidAdmin(admin.ModelAdmin):
    list_display = ["id", "custom_request", "artist", "amount", "status", "created_at", "updated_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["custom_request__title", "artist__username", "message"]
    autocomplete_fields = ["custom_request", "artist"]


@admin.register(CommissionInvitation)
class CommissionInvitationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "custom_request",
        "artist",
        "invited_by",
        "amount",
        "status",
        "responded_at",
        "created_at",
    ]
    list_filter = ["status", "created_at", "responded_at"]
    search_fields = ["custom_request__title", "artist__username", "invited_by__username", "message"]
    autocomplete_fields = ["custom_request", "artist", "invited_by"]
>>>>>>> origin/group_code


@admin.register(CommissionOption)
class CommissionOptionAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "title", "price_label", "sort_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "title", "price_label"]
