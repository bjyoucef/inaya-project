# medical/admin.py
from django.contrib import admin
from .models import Medecin

@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    search_fields = (
        "personnel__user__first_name",
        "personnel__user__last_name",
    )
    autocomplete_fields = ("personnel",)
    list_display = ("personnel", "specialite")
