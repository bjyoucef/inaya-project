from django.db import models
from django.contrib.auth.models import User


class ExportHistory(models.Model):
    """Historique des exports effectués"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exported_models = models.TextField(help_text="Modèles exportés (JSON)")
    export_format = models.CharField(
        max_length=10, choices=[("csv", "CSV"), ("excel", "Excel"), ("json", "JSON")]
    )
    file_path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    records_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Historique d'export"
        verbose_name_plural = "Historiques d'exports"

    def __str__(self):
        return f"Export {self.export_format} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
