from django.contrib import admin

from medical.models.services import Service
from .models.actes import Prestation, PrestationActe


@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "medecin",
        "date_prestation",
        "statut",
        "prix_total",
    )
    list_filter = ("statut", "date_prestation")
    search_fields = ("patient__nom", "medecin__personnel__nom")
    autocomplete_fields = ("patient", "medecin")


@admin.register(PrestationActe)
class PrestationActeAdmin(admin.ModelAdmin):
    list_display = ("prestation", "acte", "tarif_conventionne", "convention")
    autocomplete_fields = ("prestation", "acte")
    
admin.site.register(Service)