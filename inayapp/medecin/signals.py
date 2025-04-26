from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Medecin
from rh.models import Personnel


@receiver(post_save, sender=Medecin)
def create_personnel_for_new_medecin(sender, instance, created, **kwargs):
    """
    À la création d'un Medecin sans personnel associé,
    on crée automatiquement un Personnel, puis on met à jour le Medecin.
    """
    if created and instance.personnel is None:
        # On génère le nom_prenom à partir du nom complet
        nom_prenom = instance.nom_complet
        p = Personnel.objects.create(
            nom_prenom=nom_prenom,
            # Vous pouvez pré-remplir d’autres champs si besoin :
            # telephone=None, poste=None, ...
        )
        instance.personnel = p
        # Éviter de ré-appeler le signal en utilisant update_fields
        instance.save(update_fields=["personnel"])
