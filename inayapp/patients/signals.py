# patients/signals.py
from datetime import timezone
import logging
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Patient, DossierMedical

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Patient)
@transaction.atomic
def handle_patient_dossier(sender, instance, created, **kwargs):
    """
    Gestion complète de la création/mise à jour des dossiers médicaux
    avec gestion des erreurs et rollback transactionnel
    """
    try:
        if created:
            # Création du dossier médical avec vérification de nullité
            dossier = DossierMedical.objects.create(
                patient=instance,
                created_by=instance.id_created_par if instance.id_created_par else None,
            )
            logger.info(f"Dossier médical créé pour le patient {instance.id}")



        else:
            # Mise à jour synchronisée optionnelle
            if hasattr(instance, "dossier_medical"):
                instance.dossier_medical.save()

    except IntegrityError as e:
        logger.error(
            f"Erreur d'intégrité : {str(e)} - Rollback de la création du patient"
        )
        instance.delete()
        raise
    except Exception as e:
        logger.error(f"Erreur critique : {str(e)}", exc_info=True)
        raise


@receiver(post_save, sender=DossierMedical)
def post_dossier_save(sender, instance, created, **kwargs):
    """Logging supplémentaire après création de dossier"""
    if created:
        logger.info(
            f"Dossier médical {instance.id} prêt pour le patient {instance.patient_id}"
        )
