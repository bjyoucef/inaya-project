# medecin.models
from django.db import models
from django.db.models import (Sum)
from pharmacies.models import ConsommationProduit


class Medecin(models.Model):
    personnel = models.OneToOneField(
        "rh.Personnel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="profil_medecin",
        verbose_name="Profil du personnel",
    )

    services = models.ManyToManyField(
        "medical.Service",
        related_name='medecins'
    )
    specialite = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Spécialité médicale"
    )

    numero_ordre = models.CharField(
        max_length=50, unique=True, null=True, blank=True, verbose_name="Numéro d'ordre"
    )

    photo_profil = models.ImageField(
        upload_to="medecins/profiles/",
        null=True,
        blank=True,
        verbose_name="Photo de profil",
    )
    disponible = models.BooleanField(
        default=True, verbose_name="Disponible pour consultations"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )

    @property
    def nom_complet(self):
        """
        Retourne le nom complet à partir de l'utilisateur lié au Personnel.
        Si aucun Personnel n'est encore associé, on renvoie une chaîne vide.
        """
        if not self.personnel or not getattr(self.personnel, "user", None):
            return ""
        p=self.personnel
        nom_prenom = p.nom_prenom
        if nom_prenom:
            return nom_prenom
        u = p.user
        first_name = u.first_name
        last_name = u.last_name
        return f"{first_name} {last_name}"

    def __str__(self):
        # Si nom_complet est vide, on affiche 'inconnu'
        nom = self.nom_complet or "inconnu"
        return f"Dr. {nom} ({self.specialite})"

    class Meta:
        verbose_name = "Médecin"
        verbose_name_plural = "Médecins"

    @property
    def solde_consommations(self):
        return (
            ConsommationProduit.objects.filter(
                prestation_acte__prestation__medecin=self
            ).aggregate(total=Sum("montant_solde"))["total"]
            or 0.00
        )
