# audit/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import AuditLog, LoginAttempt, AuditConfiguration
import json


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp",
        "username",
        "action",
        "object_repr",
        "ip_address",
        "status_code",
    ]
    list_filter = ["action", "timestamp", "app_label", "model_name"]
    search_fields = ["username", "object_repr", "ip_address"]
    readonly_fields = [
        "timestamp",
        "user",
        "username",
        "action",
        "content_type",
        "object_id",
        "object_repr",
        "changes",
        "session_key",
        "ip_address",
        "user_agent",
        "url",
        "method",
        "status_code",
    ]

    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "content_type")

    def changes_display(self, obj):
        if obj.changes:
            formatted = json.dumps(obj.changes, indent=2, ensure_ascii=False)
            return format_html("<pre>{}</pre>", formatted)
        return "-"

    changes_display.short_description = "Changements"

    fieldsets = (
        (
            "Informations générales",
            {"fields": ("timestamp", "user", "username", "action")},
        ),
        ("Objet concerné", {"fields": ("content_type", "object_id", "object_repr")}),
        ("Détails", {"fields": ("changes_display",)}),
        (
            "Informations de session",
            {
                "fields": (
                    "session_key",
                    "ip_address",
                    "user_agent",
                    "url",
                    "method",
                    "status_code",
                )
            },
        ),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp",
        "username",
        "successful",
        "ip_address",
        "failure_reason",
    ]
    list_filter = ["successful", "timestamp"]
    search_fields = ["username", "ip_address"]
    readonly_fields = [
        "username",
        "ip_address",
        "user_agent",
        "timestamp",
        "successful",
        "failure_reason",
    ]

    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AuditConfiguration)
class AuditConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        "content_type",
        "is_active",
        "track_create",
        "track_update",
        "track_delete",
        "track_view",
    ]
    list_filter = [
        "is_active",
        "track_create",
        "track_update",
        "track_delete",
        "track_view",
    ]
    search_fields = ["content_type__model"]

    fieldsets = (
        ("Configuration générale", {"fields": ("content_type", "is_active")}),
        (
            "Actions à traquer",
            {"fields": ("track_create", "track_update", "track_delete", "track_view")},
        ),
        (
            "Champs exclus",
            {
                "fields": ("excluded_fields",),
                "description": "Liste des noms de champs à exclure de l'audit (format JSON)",
            },
        ),
    )
