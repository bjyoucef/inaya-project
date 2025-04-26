from django.apps import AppConfig


class MedecinConfig(AppConfig):
    name = "medecin"
    verbose_name = "Médecins"

    def ready(self):
        # importe le signal pour qu'il soit enregistré
        import medecin.signals
