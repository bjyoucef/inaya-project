from django.contrib import admin

from medical.models.services import Service



# Ajouter dans ServiceAdmin
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    search_fields = ["nom", "code"]  # Ajout nécessaire pour autocomplete
    # ... autres configurations ...
