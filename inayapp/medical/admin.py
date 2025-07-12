from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Service
from .resources import ServiceResource


@admin.register(Service)
class ServiceAdmin(ImportExportModelAdmin):
    resource_class = ServiceResource
    list_display = ("name", "color", "est_stockeur", "est_pharmacies", "est_hospitalier")
    list_filter = ("est_stockeur", "est_pharmacies", "est_hospitalier")
    search_fields = ("name",)
