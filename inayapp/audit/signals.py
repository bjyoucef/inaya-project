# audit/signals.py
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import AuditConfiguration
from .utils import create_audit_log, get_model_changes

# Dictionnaire pour stocker les instances avant modification
_pre_save_instances = {}


@receiver(pre_save)
def capture_pre_save_instance(sender, instance, **kwargs):
    """Capture l'instance avant sauvegarde pour détecter les changements"""
    if hasattr(instance, "_state") and instance._state.adding:
        return  # Nouvelle instance, pas besoin de capturer

    # Vérifier si l'audit est configuré pour ce modèle
    content_type = ContentType.objects.get_for_model(sender)
    try:
        config = AuditConfiguration.objects.get(content_type=content_type)
        if not config.is_active or not config.track_update:
            return
    except AuditConfiguration.DoesNotExist:
        return

    # Capturer l'instance actuelle
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        _pre_save_instances[f"{sender.__name__}_{instance.pk}"] = old_instance
    except sender.DoesNotExist:
        pass


@receiver(post_save)
def audit_model_save(sender, instance, created, **kwargs):
    """Audit automatique lors de la sauvegarde d'un modèle"""
    # Éviter les modèles d'audit
    if sender._meta.app_label == "audit":
        return

    # Vérifier si l'audit est configuré
    content_type = ContentType.objects.get_for_model(sender)
    try:
        config = AuditConfiguration.objects.get(content_type=content_type)
        if not config.is_active:
            return

        if created and not config.track_create:
            return
        elif not created and not config.track_update:
            return
    except AuditConfiguration.DoesNotExist:
        return

    if created:
        create_audit_log(instance, "CREATE")
    else:
        # Récupérer l'ancienne instance
        key = f"{sender.__name__}_{instance.pk}"
        old_instance = _pre_save_instances.get(key)

        if old_instance:
            changes = get_model_changes(old_instance, instance, config.excluded_fields)
            if changes:
                create_audit_log(instance, "UPDATE", changes)

            # Nettoyer
            del _pre_save_instances[key]


@receiver(post_delete)
def audit_model_delete(sender, instance, **kwargs):
    """Audit automatique lors de la suppression d'un modèle"""
    # Éviter les modèles d'audit
    if sender._meta.app_label == "audit":
        return

    # Vérifier si l'audit est configuré
    content_type = ContentType.objects.get_for_model(sender)
    try:
        config = AuditConfiguration.objects.get(content_type=content_type)
        if not config.is_active or not config.track_delete:
            return
    except AuditConfiguration.DoesNotExist:
        return

    create_audit_log(instance, "DELETE")
