from django.contrib import admin
from .models import  DossierMedical, Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "last_name",
        "first_name",
        "date_of_birth",
        "gender",
        "phone_number",
        "is_active",
    )
    list_filter = ("gender", "is_active", "created_at")
    search_fields = ("last_name", "first_name", "social_security_number")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


# admin.py


@admin.register(DossierMedical)
class DossierMedicalAdmin(admin.ModelAdmin):
    list_display = ("patient", "groupe_sanguin", "poids", "taille")
    search_fields = ("patient__nom", "patient__prenom")


