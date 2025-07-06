# audit/reports.py
from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import csv
import json
from .models import AuditLog, LoginAttempt


class AuditReporter:
    """Classe pour générer des rapports d'audit"""

    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date or timezone.now()

        if not self.start_date:
            self.start_date = self.end_date - timedelta(days=30)

    def get_queryset(self):
        """Obtient le queryset filtré par date"""
        return AuditLog.objects.filter(
            timestamp__gte=self.start_date, timestamp__lte=self.end_date
        )

    def generate_summary_report(self):
        """Génère un rapport de synthèse"""
        qs = self.get_queryset()

        summary = {
            "period": {
                "start": self.start_date.isoformat(),
                "end": self.end_date.isoformat(),
            },
            "total_logs": qs.count(),
            "unique_users": qs.values("user").distinct().count(),
            "actions_breakdown": list(
                qs.values("action").annotate(count=Count("id")).order_by("-count")
            ),
            "top_users": list(
                qs.values("username")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            ),
            "apps_breakdown": list(
                qs.values("app_label").annotate(count=Count("id")).order_by("-count")
            ),
            "models_breakdown": list(
                qs.values("model_name").annotate(count=Count("id")).order_by("-count")
            ),
            "failed_logins": LoginAttempt.objects.filter(
                timestamp__gte=self.start_date,
                timestamp__lte=self.end_date,
                successful=False,
            ).count(),
        }

        return summary

    def export_to_csv(self, response):
        """Exporte les logs en CSV"""
        writer = csv.writer(response)
        writer.writerow(
            [
                "Timestamp",
                "User",
                "Action",
                "Object",
                "App",
                "Model",
                "IP Address",
                "Changes",
            ]
        )

        for log in self.get_queryset().select_related("user", "content_type"):
            writer.writerow(
                [
                    log.timestamp.isoformat(),
                    log.username,
                    log.get_action_display(),
                    log.object_repr,
                    log.app_label,
                    log.model_name,
                    log.ip_address,
                    json.dumps(log.changes) if log.changes else "",
                ]
            )

        return response

    def export_to_json(self, response):
        """Exporte les logs en JSON"""
        logs = []
        for log in self.get_queryset().select_related("user", "content_type"):
            logs.append(
                {
                    "timestamp": log.timestamp.isoformat(),
                    "user": log.username,
                    "action": log.action,
                    "object": log.object_repr,
                    "app": log.app_label,
                    "model": log.model_name,
                    "ip_address": log.ip_address,
                    "changes": log.changes,
                    "url": log.url,
                    "method": log.method,
                }
            )

        json.dump(logs, response, indent=2, ensure_ascii=False)
        return response
