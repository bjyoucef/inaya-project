# audit/management/commands/setup_audit.py
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from audit.models import AuditConfiguration


class Command(BaseCommand):
    help = "Configure l'audit pour tous les modèles du projet"

    def add_arguments(self, parser):
        parser.add_argument(
            "--enable-all",
            action="store_true",
            help="Active l'audit pour tous les modèles",
        )
        parser.add_argument(
            "--app",
            type=str,
            help="Configure l'audit pour une application spécifique",
        )

    def handle(self, *args, **options):
        if options["enable_all"]:
            self.setup_all_models()
        elif options["app"]:
            self.setup_app_models(options["app"])
        else:
            self.stdout.write(
                self.style.ERROR("Utilisez --enable-all ou --app <nom_app>")
            )

    def setup_all_models(self):
        """Configure l'audit pour tous les modèles"""
        count = 0
        for model in apps.get_models():
            if model._meta.app_label == "audit":
                continue  # Éviter les modèles d'audit

            content_type = ContentType.objects.get_for_model(model)
            config, created = AuditConfiguration.objects.get_or_create(
                content_type=content_type,
                defaults={
                    "is_active": True,
                    "track_create": True,
                    "track_update": True,
                    "track_delete": True,
                    "track_view": False,
                },
            )

            if created:
                count += 1
                self.stdout.write(f"Configuration créée pour {model._meta.label}")

        self.stdout.write(self.style.SUCCESS(f"Audit configuré pour {count} modèles"))

    def setup_app_models(self, app_name):
        """Configure l'audit pour les modèles d'une application"""
        try:
            app = apps.get_app_config(app_name)
        except LookupError:
            self.stdout.write(self.style.ERROR(f"Application {app_name} non trouvée"))
            return

        count = 0
        for model in app.get_models():
            content_type = ContentType.objects.get_for_model(model)
            config, created = AuditConfiguration.objects.get_or_create(
                content_type=content_type,
                defaults={
                    "is_active": True,
                    "track_create": True,
                    "track_update": True,
                    "track_delete": True,
                    "track_view": False,
                },
            )

            if created:
                count += 1
                self.stdout.write(f"Configuration créée pour {model._meta.label}")

        self.stdout.write(
            self.style.SUCCESS(f"Audit configuré pour {count} modèles dans {app_name}")
        )
