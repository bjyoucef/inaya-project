from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import json


class AuditLog(models.Model):
    """Modèle principal pour enregistrer tous les audits"""

    ACTION_CHOICES = [
        ("CREATE", "Création"),
        ("UPDATE", "Modification"),
        ("DELETE", "Suppression"),
        ("VIEW", "Consultation"),
        ("LOGIN", "Connexion"),
        ("LOGOUT", "Déconnexion"),
        ("FAILED_LOGIN", "Tentative de connexion échouée"),
        ("PERMISSION_DENIED", "Accès refusé"),
        ("EXPORT", "Export de données"),
        ("IMPORT", "Import de données"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    username = models.CharField(
        max_length=150, blank=True
    )  # Garde le nom même si user supprimé
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)

    # Objet concerné par l'audit
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Détails de l'action
    object_repr = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(
        default=dict, blank=True
    )  # Anciennes et nouvelles valeurs

    # Informations de session
    session_key = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Informations supplémentaires
    url = models.URLField(blank=True)
    method = models.CharField(max_length=10, blank=True)
    status_code = models.IntegerField(null=True, blank=True)

    # Métadonnées
    app_label = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Log d'audit"
        verbose_name_plural = "Logs d'audit"
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.action} - {self.timestamp}"


class LoginAttempt(models.Model):
    """Modèle pour traquer les tentatives de connexion"""

    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    successful = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["username", "timestamp"]),
            models.Index(fields=["ip_address", "timestamp"]),
        ]

    def __str__(self):
        status = "Succès" if self.successful else "Échec"
        return f"{self.username} - {status} - {self.timestamp}"


class AuditConfiguration(models.Model):
    """Configuration de l'audit pour chaque modèle"""

    content_type = models.OneToOneField(
        ContentType, on_delete=models.CASCADE, unique=True
    )
    is_active = models.BooleanField(default=True)
    track_create = models.BooleanField(default=True)
    track_update = models.BooleanField(default=True)
    track_delete = models.BooleanField(default=True)
    track_view = models.BooleanField(default=False)
    excluded_fields = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Configuration d'audit"
        verbose_name_plural = "Configurations d'audit"

    def __str__(self):
        return f"Audit {self.content_type.model}"
