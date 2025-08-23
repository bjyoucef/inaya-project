from django.db import models
from django.core.validators import RegexValidator
from django.db.models import Sum
from pharmacies.models import ConsommationProduit
from pharmacies.models import Produit


class Medecin(models.Model):
    first_name = models.CharField(max_length=50, null=True, blank=True, verbose_name="Prénom")
    last_name = models.CharField(max_length=50, null=True, blank=True, verbose_name="Nom")
    email = models.EmailField(max_length=254, null=True, blank=True, verbose_name="Email")
    services = models.ManyToManyField("medical.Service", related_name="medecins")
    specialite = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Spécialité médicale"
    )

    telephone = models.CharField(
        max_length=15,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?\d{9,15}$",
                message="Le numéro de téléphone doit être au format +213123456789 (9 à 15 chiffres).",
            )
        ],
        verbose_name="Numéro de téléphone",
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        verbose_name="Créé par"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )
    @property
    def nom_complet(self):
        first_name = self.first_name or ""
        last_name = self.last_name or ""
        return f"{first_name} {last_name}"

    def __str__(self):
        # Si nom_complet est vide, on affiche 'inconnu'
        nom = self.nom_complet or "inconnu"
        telephone = f" ({self.telephone})" if self.telephone else ""
        return f"Dr. {nom} ({self.specialite or 'N/A'}){telephone}"

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
