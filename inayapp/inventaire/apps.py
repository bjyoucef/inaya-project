# inventaire/apps.py
from django.apps import AppConfig


class InventaireConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventaire"
    verbose_name = "Gestion Inventaire"
