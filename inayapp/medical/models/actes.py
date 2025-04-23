# medical.models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone

from finance.models import TarifActeConvention


class Acte(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    service = models.ForeignKey("Service", on_delete=models.PROTECT, related_name="actes")

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    class Meta:
        verbose_name = "Acte"
        verbose_name_plural = "Actes"


class Prestation(models.Model):
    STATUT_CHOICES = [
        ("PLANIFIE", "Planifié"),
        ("REALISE", "Réalisé"),
        ("FACTURE", "Facturé"),
        ("ANNULE", "Annulé"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name="Patient",
    )
    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name="Médecin traitant",
    )
    actes = models.ManyToManyField(
        "Acte",
        through="PrestationActe",
        related_name="prestations",
        verbose_name="Actes médicaux",
    )
    date_prestation = models.DateTimeField(
        default=timezone.now, verbose_name="Date de réalisation"
    )

    statut = models.CharField(
        max_length=25,
        choices=STATUT_CHOICES,
        default="PLANIFIE",
        verbose_name="Statut de la prestation",
    )
    prix_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Coût total",
        validators=[MinValueValidator(0)],
    )

    observations = models.TextField(blank=True, verbose_name="Observations médicales")


    class Meta:
        verbose_name = "Prestation médicale"
        verbose_name_plural = "Prestations médicales"
        ordering = ["-date_prestation"]
        indexes = [
            models.Index(fields=["date_prestation"]),
            models.Index(fields=["statut"]),
            models.Index(fields=["patient"]),
        ]


    def __str__(self):
        return f"Prestation #{self.id} - {self.patient} ({self.date_prestation.date()})"


    @property
    def details_actes(self):
        return "\n".join(
            f"{pa.acte} ({pa.tarif_conventionne}€)"
            for pa in self.prestationacte_set.all()
        )

    @property
    def dossier_medical(self):
        return self.patient.dossier_medical


class PrestationActe(models.Model):
    prestation = models.ForeignKey(
        Prestation, on_delete=models.CASCADE, related_name="actes_details"
    )
    acte = models.ForeignKey(
        "Acte", on_delete=models.PROTECT, related_name="prestations_liees"
    )
    convention = models.ForeignKey(
        "finance.Convention",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestations",
        verbose_name="Convention appliquée",
    )
    tarif_conventionne = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Tarif conventionné"
    )

    commentaire = models.TextField(blank=True, verbose_name="Commentaire médical")

    class Meta:
        verbose_name = "Détail d'acte"
        verbose_name_plural = "Détails des actes"
        unique_together = ("prestation", "acte")

    def __str__(self):
        return f"{self.acte} - {self.prestation}"

    def save(self, *args, **kwargs):
        if not self.tarif_conventionne:
            self.tarif_conventionne = self._get_tarif_applicable()
        super().save(*args, **kwargs)



    def _get_tarif_applicable(self):
        """Récupère le tarif selon la convention ou le tarif de base"""
        if self.convention:
            tarif = (
                TarifActeConvention.objects.filter(
                    convention=self.convention, acte=self.acte
                )
                .order_by("-date_effective")
                .first()
            )
            if tarif:
                return tarif.tarif_acte.montant
        return self.acte.tarifs.latest().montant
