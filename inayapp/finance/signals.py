from django.db.models.signals import pre_save
from django.dispatch import receiver

from medical.models.prestation_Kt import TarifActe


@receiver(pre_save, sender=TarifActe)
def ensure_single_default(sender, instance, **kwargs):
    if instance.is_default:
        # désactive tous les autres pour le même acte
        sender.objects.filter(acte=instance.acte, is_default=True).update(
            is_default=False
        )
