from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Service
from .resources import ServiceResource


@admin.register(Service)
class ServiceAdmin(ImportExportModelAdmin):
    resource_class = ServiceResource
    list_display = ("name", "color", "est_stockeur")
    list_editable = ("color", "est_stockeur")
    search_fields = ("name",)
