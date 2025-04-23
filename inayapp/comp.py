from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from finance.models import TarifActeConvention


class Acte(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    service = models.ForeignKey(
        "Service", on_delete=models.PROTECT, related_name="actes"
    )

    def __str__(self):
        return f"{self.code} – {self.libelle}"

    class Meta:
        verbose_name = "Acte"
        verbose_name_plural = "Actes"


class Prestation(models.Model):
    STATUT_CHOICES = [
        ("PLANIFIE", "Planifié"),
        ("REALISE", "Réalisé"),
        ("FACTURE", "Facturé"),
        ("PARTIELLEMENT_REMBOURSE", "Partiellement remboursé"),
        ("ANNULE", "Annulé"),
    ]
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="prestations"
    )
    medecin = models.ForeignKey(
        "medecin.Medecin", on_delete=models.PROTECT, related_name="prestations"
    )
    actes = models.ManyToManyField(
        "Acte", through="PrestationActe", related_name="prestations"
    )
    date_prestation = models.DateTimeField(default=timezone.now)
    date_facturation = models.DateTimeField(null=True, blank=True)
    convention = models.ForeignKey(
        "finance.Convention", on_delete=models.SET_NULL, null=True, blank=True
    )
    statut = models.CharField(max_length=25, choices=STATUT_CHOICES, default="PLANIFIE")
    prix_total = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    prise_en_charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    taux_remboursement = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    reste_a_charge = models.DecimalField(
        max_digits=10, decimal_places=2, editable=False
    )

    def __str__(self):
        return f"Prestation #{self.id} – {self.patient}"

    def save(self, *args, **kwargs):
        # recalcul des montants
        total = sum(
            pa.tarif_conventionne * pa.quantite for pa in self.prestationacte_set.all()
        )
        self.prix_total = total
        remb = (total * self.taux_remboursement) / 100
        self.prise_en_charge = min(remb, total)
        self.reste_a_charge = total - self.prise_en_charge
        super().save(*args, **kwargs)

    def clean(self):
        if self.prise_en_charge > self.prix_total:
            raise ValidationError("La prise en charge ne peut excéder le coût total")


class PrestationActe(models.Model):
    prestation = models.ForeignKey(
        Prestation, on_delete=models.CASCADE, related_name="actes_details"
    )
    acte = models.ForeignKey(
        Acte, on_delete=models.PROTECT, related_name="prestations_liees"
    )
    tarif_conventionne = models.DecimalField(max_digits=10, decimal_places=2)
    quantite = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    remboursable = models.BooleanField(default=True)
    commentaire = models.TextField(blank=True)

    class Meta:
        unique_together = ("prestation", "acte")

    def __str__(self):
        return f"{self.acte} ×{self.quantite}"
