from django.contrib import admin
from .models import ExportHistory


@admin.register(ExportHistory)
class ExportHistoryAdmin(admin.ModelAdmin):
    list_display = ["user", "export_format", "records_count", "created_at"]
    list_filter = ["export_format", "created_at"]
    search_fields = ["user__username"]
    readonly_fields = ["created_at"]

    def has_add_permission(self, request):
        return False
