# patients/apps.py
from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "patients"

    def ready(self):
        # Import des signaux
        import patients.signals
