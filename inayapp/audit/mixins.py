# audit/mixins.py
from django.db import models
from django.contrib.contenttypes.models import ContentType
from .utils import create_audit_log, get_model_changes
from .models import AuditConfiguration


class AuditMixin(models.Model):
    """Mixin pour ajouter l'audit automatique aux modèles"""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Déterminer si c'est une création ou une mise à jour
        is_create = self.pk is None

        # Pour les mises à jour, obtenir l'ancienne version
        old_instance = None
        if not is_create:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                is_create = True

        # Sauvegarder l'objet
        super().save(*args, **kwargs)

        # Créer le log d'audit
        if is_create:
            create_audit_log(self, "CREATE")
        else:
            # Obtenir la configuration d'audit
            content_type = ContentType.objects.get_for_model(self)
            try:
                config = AuditConfiguration.objects.get(content_type=content_type)
                excluded_fields = config.excluded_fields
            except AuditConfiguration.DoesNotExist:
                excluded_fields = []

            changes = get_model_changes(old_instance, self, excluded_fields)
            if changes:  # Ne log que s'il y a des changements
                create_audit_log(self, "UPDATE", changes)

    def delete(self, *args, **kwargs):
        # Créer le log avant la suppression
        create_audit_log(self, "DELETE")
        super().delete(*args, **kwargs)
