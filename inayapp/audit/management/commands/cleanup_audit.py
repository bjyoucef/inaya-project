# audit/management/commands/cleanup_audit.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from audit.models import AuditLog, LoginAttempt


class Command(BaseCommand):
    help = "Nettoie les anciens logs d'audit"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Supprime les logs plus anciens que X jours",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche ce qui serait supprimé sans supprimer",
        )

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(days=options["days"])

        # Compter les logs à supprimer
        audit_logs_count = AuditLog.objects.filter(timestamp__lt=cutoff_date).count()

        login_attempts_count = LoginAttempt.objects.filter(
            timestamp__lt=cutoff_date
        ).count()

        if options["dry_run"]:
            self.stdout.write(f"Logs d'audit à supprimer: {audit_logs_count}")
            self.stdout.write(
                f"Tentatives de connexion à supprimer: {login_attempts_count}"
            )
            self.stdout.write(
                self.style.WARNING("Mode dry-run: aucune suppression effectuée")
            )
        else:
            # Supprimer les logs
            AuditLog.objects.filter(timestamp__lt=cutoff_date).delete()
            LoginAttempt.objects.filter(timestamp__lt=cutoff_date).delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Supprimé {audit_logs_count} logs d'audit et "
                    f"{login_attempts_count} tentatives de connexion"
                )
            )
