# finance/models.py

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone


class Decharges(models.Model):
    id_decharge = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    id_created_par = models.ForeignKey(
        User, models.DO_NOTHING, db_column="id_created_par", blank=True, null=True
    )
    time_export_decharge_pdf = models.DateTimeField(blank=True, null=True)
    id_export_par = models.ForeignKey(
        User,
        models.DO_NOTHING,
        db_column="id_export_par",
        related_name="decharges_id_export_par_set",
        blank=True,
        null=True,
    )
    prestation_actes = models.ManyToManyField(
        "medical.PrestationActe", related_name="decharges", verbose_name="Prestations associées"
    )
    # Modifier le champ id_doctor en ForeignKey
    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="decharges",
        verbose_name="Médecin",
        blank=True,
        null=True,
    )
    id_employe = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = True


class Payments(models.Model):
    id_payment = models.AutoField(primary_key=True)
    id_decharge = models.ForeignKey(
        "Decharges",
        models.DO_NOTHING,
        db_column="id_decharge",
        related_name="payments",
        blank=True,
        null=True,
        default=None,  # Add this explicitly
    )
    payment = models.DecimalField(max_digits=10, decimal_places=2)
    time_payment = models.DateTimeField(blank=True, null=True)
    id_payment_par = models.ForeignKey(
        "rh.Personnel",
        models.DO_NOTHING,
        db_column="id_payment_par",
        related_name="decharges_id_payment_par_set",
        blank=True,
        null=True,
    )

    class Meta:
        managed = True


class Tarif_Gardes(models.Model):
    poste = models.ForeignKey(
        "rh.Poste", on_delete=models.CASCADE, related_name="tarifs"
    )
    service = models.ForeignKey(
        "medical.Service", on_delete=models.CASCADE, related_name="tarifs"
    )
    shift = models.ForeignKey(
        "rh.Shift",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tarifs",
    )
    prix = models.DecimalField(
        "Prix (€)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    salaire = models.DecimalField(
        "Salaire (€)", max_digits=12, decimal_places=2, null=True, blank=True
    )

    class Meta:
        unique_together = ("poste", "service", "shift")
        verbose_name = "Tarif_Gardes"
        verbose_name_plural = "Tarif_Gardes"

    def __str__(self):
        desc = f"{self.poste} / {self.service}"
        if self.shift:
            desc += f" ({self.shift})"
        return desc


class TarifActe(models.Model):
    acte = models.ForeignKey(
        "medical.Acte", on_delete=models.CASCADE, related_name="tarifs"
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    montant_honoraire_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Montant d’honoraire de base applicable hors convention",
    )
    date_effective = models.DateField(default=timezone.now)
    is_default = models.BooleanField(
        default=False,
        help_text="Cocher pour ce tarif soit celui par défaut pour l’acte",
    )

    def __str__(self):
        return str(self.montant)

    class Meta:
        verbose_name = "Tarif de base"
        verbose_name_plural = "Tarifs de base"
        ordering = ["-is_default", "-date_effective"]


class Convention(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    actes = models.ManyToManyField(
        "medical.Acte", through="TarifActeConvention", related_name="conventions"
    )

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Convention"
        verbose_name_plural = "Conventions"


class TarifActeConvention(models.Model):
    convention = models.ForeignKey(
        "Convention", on_delete=models.CASCADE, related_name="tarifs"
    )
    acte = models.ForeignKey(
        "medical.Acte", on_delete=models.CASCADE, related_name="tarifs_convention"
    )
    tarif_acte = models.ForeignKey(
        "TarifActe",
        on_delete=models.CASCADE,
        related_name="tarifs_par_convention",
    )
    date_effective = models.DateField(default=timezone.now)
    montant_honoraire_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Montant de l'honoraire de base pour cet acte et cette convention",
    )

    class Meta:
        unique_together = ("convention", "acte", "date_effective")
        verbose_name = "Tarif par convention"
        verbose_name_plural = "Tarifs par convention"
        ordering = ["-date_effective"]

    def __str__(self):
        return (
            f"{self.convention.nom} - {self.acte.code} : {self.montant_honoraire_base}€"
        )


class PrixSupplementaireConfig(models.Model):
    """
    Configuration du pourcentage de prix supplémentaire par médecin.
    Par exemple, si pourcentage = 10.5, on ajoutera 10.5% au tarif de base.
    """

    medecin = models.OneToOneField(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="prix_supplementaire_config",
        verbose_name="Médecin",
    )
    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Pourcentage supplémentaire (%)",
        help_text="Pourcentage à appliquer sur le prix supplémentaire par médecin.",
    )

    class Meta:
        verbose_name = "Configuration Prix Supplémentaire"
        verbose_name_plural = "Configurations Prix Supplémentaires"


class HonorairesMedecinManager(models.Manager):
    def get_tarif_effectif(self, medecin, acte, convention, date_reference):
        """Retourne la configuration valide à une date donnée"""
        return (
            self.filter(
                medecin=medecin,
                acte=acte,
                convention=convention,
                date_effective__lte=date_reference,
            )
            .order_by("-date_effective")
            .first()
        )


class HonorairesMedecin(models.Model):
    """Configuration des honoraires par médecin, acte et convention"""

    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="honoraires_configures",
        verbose_name="Médecin",
    )
    acte = models.ForeignKey(
        "medical.Acte",
        on_delete=models.CASCADE,
        related_name="honoraires_medecins",
        verbose_name="Acte médical",
    )
    convention = models.ForeignKey(
        "Convention",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="honoraires_medecins",
        verbose_name="Convention appliquée",
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Tarif appliqué",
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    date_effective = models.DateField(default=timezone.now, verbose_name="Date d'effet")

    objects = HonorairesMedecinManager()

    class Meta:
        verbose_name = "Config honoraire médecin"
        verbose_name_plural = "Config honoraires médecins"
        unique_together = ("medecin", "acte", "convention", "date_effective")
        ordering = ["-date_effective"]

    def __str__(self):
        convention = f" - {self.convention.nom}" if self.convention else ""
        return f"{self.medecin} - {self.acte.code}{convention} | {self.montant}DA ({self.date_effective})"

    def clean(self):
        """Validation supplémentaire"""
        if self.montant < Decimal("0"):
            raise ValidationError("Le montant ne peut pas être négatif")


# finance/models.py
class BonDePaiement(models.Model):
    METHODE_CHOICES = [
        ("ESP", "Espèces"),
        ("CHQ", "Chèque"),
        ("CB", "Carte Bancaire"),
    ]

    prestation = models.ForeignKey(
        "medical.Prestation", on_delete=models.PROTECT, related_name="bons_de_paiement"
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(default=timezone.now)
    encaisse_par = models.ForeignKey(User, on_delete=models.PROTECT)
    methode = models.CharField(max_length=10, choices=METHODE_CHOICES, default="ESP")
    reference = models.CharField(max_length=50, unique=True, blank=True)

    def __str__(self):
        return f"Bon #{self.reference} - {self.montant}€"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Génération automatique de la référence
            date_part = timezone.now().strftime("%Y%m%d")
            last_id = BonDePaiement.objects.count() + 1
            self.reference = f"BON-{date_part}-{last_id:05d}"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Bon de paiement"
        verbose_name_plural = "Bons de paiement"
