from django.apps import AppConfig


class AccueilConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accueil"
    def ready(self):
        import accueil.signals
