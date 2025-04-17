from django.contrib import admin
from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "last_name",
        "first_name",
        "date_of_birth",
        "gender",
        "phone_number",
    )
    search_fields = ("last_name", "first_name", "phone_number")
    list_filter = ("gender",)
    ordering = ("last_name",)
