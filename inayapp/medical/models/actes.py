# medical.models
from decimal import Decimal
from django.db.models import F

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from finance.models import (
    HonorairesMedecin,
    TarifActeConvention,
    TarifActe,
)
from pharmacies.models.stock import ConsommationProduit, Stock
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()

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
    )
    prix_supplementaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Frais supplémentaires",
        help_text="Coût supplémentaire pour la prestation (hors actes et consommations)"
    )
    prix_supplementaire_medecin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0,
        verbose_name="Part médecin du supplément"
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
            f"{pa.acte} ({pa.tarif_conventionne}DA)"
            for pa in self.prestationacte_set.all()
        )

    @property
    def dossier_medical(self):
        return self.patient.dossier_medical

    def cancel_stock_impact(self):
        """Annule l'impact précédent sur le stock"""
        for pa in self.actes_details.all():
            for conso in pa.consommations.all():
                service = pa.acte.service
                try:
                    stock = Stock.objects.get(produit=conso.produit, service=service)
                    stock.quantite += conso.quantite_reelle
                    stock.save()
                except Stock.DoesNotExist:
                    pass


    def update_stock(self):
        """Met à jour le stock par service concerné"""
        for pa in self.actes_details.all():
            for conso in pa.consommations.all():
                service = pa.acte.service
                # ← change get_or_create to filter/create
                qs = Stock.objects.filter(produit=conso.produit, service=service)
                if not qs.exists():
                    # no stock row → create one
                    stock = Stock.objects.create(
                        produit=conso.produit, service=service, quantite=0
                    )
                    qs = [stock]
                # now qs is either the newly created or the existing QuerySet
                for stock in qs:
                    stock.quantite -= conso.quantite_reelle
                    stock.save()

    def calculate_total_price(self):
        """Calcule le prix total incluant les actes, les consommations et les frais supplémentaires"""
        total = Decimal("0.00")

        # Prix des actes
        for pa in self.actes_details.all():
            total += pa.tarif_conventionne

            # Prix des consommations de produits
            for conso in pa.consommations.all():
                quantite_supplementaire = max(
                    0, conso.quantite_reelle - conso.quantite_defaut
                )
                total += quantite_supplementaire * conso.prix_unitaire

        # Ajouter les frais supplémentaires
        total += self.prix_supplementaire

        return total

    def update_total_price(self):
        """Met à jour le prix total de la prestation"""
        self.prix_total = self.calculate_total_price()
        self.save(update_fields=["prix_total"])


class PrestationActe(models.Model):
    prestation = models.ForeignKey(
        "Prestation", on_delete=models.CASCADE, related_name="actes_details"
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
    convention_accordee = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Statut Convention",
        help_text="Uniquement si une convention est sélectionnée",
    )
    honoraire_medecin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Honoraire médecin",
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("99999999.99")),
        ],
    )
    commentaire = models.TextField(blank=True, verbose_name="Commentaire médical")

    class Meta:
        verbose_name = "Détail d'acte"
        verbose_name_plural = "Détails des actes"

    def __str__(self):
        return f"{self.acte} - {self.prestation}"

    def save(self, *args, **kwargs):
        if not self.tarif_conventionne:
            self.tarif_conventionne = self._get_tarif_applicable()

        if not self.honoraire_medecin:
            self._calculate_honoraire_medecin()
        super().save(*args, **kwargs)

    def _calculate_honoraire_medecin(self):
        """
        1) Tarif médecin spécifique
        2) montant_honoraire_base depuis TarifActeConvention
        3) montant_honoraire_base dans TarifActe (si pas de convention ou pas trouvé)
        """
        # 1️⃣ Tarif médecin spécifique
        honoraire_config = HonorairesMedecin.objects.get_tarif_effectif(
            medecin=self.prestation.medecin,
            acte=self.acte,
            convention=self.convention,
            date_reference=self.prestation.date_prestation,
        )
        if honoraire_config:
            self.honoraire_medecin = honoraire_config.montant
            return

        # 2️⃣ Honoraire de base acte-convention
        if self.convention:
            base_hon = (
                TarifActeConvention.objects.filter(
                    convention=self.convention,
                    acte=self.acte,
                    date_effective__lte=self.prestation.date_prestation,
                )
                .order_by("-date_effective")
                .first()
            )
            if base_hon and base_hon.montant_honoraire_base > Decimal("0"):
                self.honoraire_medecin = base_hon.montant_honoraire_base
                return

        # 3️⃣ Honoraire de base depuis le TarifActe (hors convention)
        tarif_acte = (
            TarifActe.objects.filter(
                acte=self.acte,
                date_effective__lte=self.prestation.date_prestation,
            )
            .order_by("-is_default", "-date_effective")
            .first()
        )
        if tarif_acte and tarif_acte.montant_honoraire_base > Decimal("0"):
            self.honoraire_medecin = tarif_acte.montant_honoraire_base

    def clean(self):
        """Validation des montants"""
        if self.tarif_conventionne < Decimal('0'):
            raise ValidationError("Le tarif ne peut pas être négatif")

        if self.honoraire_medecin < Decimal('0'):
            raise ValidationError("L'honoraire médecin ne peut pas être négatif")

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

    def get_produits_defaut(self):
        """Récupère les produits par défaut avec leur quantité"""
        return self.acte.produits_defaut.all()


class ActeProduit(models.Model):
    acte = models.ForeignKey(
        "Acte",
        on_delete=models.CASCADE,
        related_name="produits_defaut",
        verbose_name="Acte médical",
    )
    produit = models.ForeignKey(
        "pharmacies.Produit", on_delete=models.PROTECT, verbose_name="Produit associé"
    )
    quantite_defaut = models.PositiveIntegerField(
        default=1, verbose_name="Quantité par défaut"
    )

    class Meta:
        verbose_name = "Produit par défaut pour acte"
        verbose_name_plural = "Produits par défaut pour actes"
        unique_together = ("acte", "produit")

    def __str__(self):
        return f"{self.acte} - {self.produit} ({self.quantite_defaut})"


class PrestationAudit(models.Model):
    prestation = models.ForeignKey(
        Prestation, on_delete=models.CASCADE, related_name="audits"
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="Utilisateur"
    )
    champ = models.CharField(max_length=100, verbose_name="Champ modifié")
    ancienne_valeur = models.TextField(
        blank=True, null=True, verbose_name="Valeur avant modification"
    )
    nouvelle_valeur = models.TextField(
        blank=True, null=True, verbose_name="Valeur après modification"
    )
    date_modification = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de modification"
    )

    class Meta:
        verbose_name = "Audit de prestation"
        verbose_name_plural = "Audits de prestations"
        ordering = ["-date_modification"]

    def __str__(self):
        return f"Audit #{self.id} - {self.champ}"
