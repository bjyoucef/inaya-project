# audit/management/commands/audit_report.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from audit.reports import AuditReporter
import json


class Command(BaseCommand):
    help = "Génère un rapport d'audit"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Nombre de jours à inclure dans le rapport",
        )
        parser.add_argument(
            "--format",
            choices=["json", "summary"],
            default="summary",
            help="Format du rapport",
        )
        parser.add_argument("--output", type=str, help="Fichier de sortie (optionnel)")

    def handle(self, *args, **options):
        end_date = timezone.now()
        start_date = end_date - timedelta(days=options["days"])

        reporter = AuditReporter(start_date, end_date)

        if options["format"] == "summary":
            report = reporter.generate_summary_report()
            output = json.dumps(report, indent=2, ensure_ascii=False, default=str)
        else:
            # Format JSON détaillé
            logs = []
            for log in reporter.get_queryset().select_related("user", "content_type"):
                logs.append(
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "user": log.username,
                        "action": log.action,
                        "object": log.object_repr,
                        "changes": log.changes,
                    }
                )
            output = json.dumps(logs, indent=2, ensure_ascii=False)

        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as f:
                f.write(output)
            self.stdout.write(
                self.style.SUCCESS(f'Rapport sauvegardé dans {options["output"]}')
            )
        else:
            self.stdout.write(output)
