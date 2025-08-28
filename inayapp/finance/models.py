# finance/models.py

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone

User = get_user_model()

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
        permissions = (
            ("create_decharge_multiple", "Peut créer plusieurs décharges à la fois"),
            ("export_decharge_pdf", "Peut exporter les décharges en PDF"),
            ("view_situation_medecins", "Peut voir la situation des médecins"),
            ("settle_decharge", "Peut régler une décharge"),
        )


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
        permissions = (
            ("validate_payment", "Peut valider un paiement"),
            ("cancel_payment", "Peut annuler un paiement"),
            ("view_payment_history", "Peut voir l'historique des paiements"),
        )


class PaiementEspecesKt(models.Model):
    """Modèle pour gérer les paiements espèces avec traçabilité complète"""

    STATUT_CHOICES = [
        ("EN_COURS", "En cours de paiement"),
        ("COMPLET", "Paiement complet"),
        ("ANNULE", "Annulé"),
    ]

    # Relation avec la prestation
    prestation = models.OneToOneField(
        "medical.PrestationKt",
        on_delete=models.CASCADE,
        related_name="paiement_especes",
        verbose_name="Prestation concernée",
    )

    # Montants
    montant_total_du = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant total dû",
        help_text="Montant total à payer en espèces",
    )

    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant déjà payé",
        help_text="Somme de tous les paiements effectués",
    )

    montant_restant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant restant",
        help_text="Montant encore à payer",
    )

    # Statut et dates
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_COURS",
        verbose_name="Statut du paiement",
    )

    date_creation = models.DateTimeField(
        default=timezone.now, verbose_name="Date de création"
    )

    date_completion = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de finalisation"
    )

    # Traçabilité
    cree_par = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="paiements_especes_crees",
        verbose_name="Créé par",
    )

    # Notes et observations
    notes = models.TextField(blank=True, verbose_name="Notes et observations")

    class Meta:
        verbose_name = "Paiement espèces"
        verbose_name_plural = "Paiements espèces"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["date_creation"]),
            models.Index(fields=["prestation"]),
        ]
        permissions = (
            ("view_paiements_especes_dashboard", "Peut voir le dashboard des paiements espèces"),
            ("export_paiements_especes", "Peut exporter les paiements espèces"),
            ("view_historique_paiements", "Peut voir l'historique des paiements"),
            ("manage_tranches_paiement", "Peut gérer les tranches de paiement"),
        )
    def __str__(self):
        return f"Paiement #{self.id} - Prestation #{self.prestation.id} - {self.montant_paye}/{self.montant_total_du} DA"

    def save(self, *args, **kwargs):
        # Calculer le montant restant
        self.montant_restant = self.montant_total_du - self.montant_paye

        # Mettre à jour le statut automatiquement
        ancien_statut = self.statut
        if self.montant_restant <= 0:
            self.statut = "COMPLET"
            if not self.date_completion:
                self.date_completion = timezone.now()
        elif self.montant_paye > 0:
            self.statut = "EN_COURS"

        super().save(*args, **kwargs)

        # CORRECTION: Mettre à jour le statut de la prestation si le paiement devient complet
        if ancien_statut != "COMPLET" and self.statut == "COMPLET":
            self.prestation.marquer_comme_payee_si_possible()

    def _recalculate_and_update(self):
        """Recalcule et met à jour le paiement avec gestion du statut de prestation"""
        # Recalculer le montant total payé
        montant_total_tranches = self.tranches.aggregate(total=models.Sum("montant"))[
            "total"
        ] or Decimal("0.00")

        ancien_statut = self.statut
        self.montant_paye = montant_total_tranches

        # Sauvegarder (cela va déclencher la logique de statut via save())
        self.save()

        # CORRECTION: Si le statut change de COMPLET vers EN_COURS,
        # vérifier si la prestation doit être remise en REALISE
        if ancien_statut == "COMPLET" and self.statut != "COMPLET":
            prestation = self.prestation
            if prestation.statut == "PAYE":
                # Vérifier s'il y a d'autres raisons de garder le statut PAYE
                if not prestation.peut_etre_marquee_payee():
                    prestation.statut = "REALISE"
                    prestation.save(update_fields=["statut"])

    @property
    def est_complet(self):
        """Vérifie si le paiement est complet"""
        return self.montant_restant <= 0

    def peut_recevoir_paiement(self, montant):
        """Vérifie si on peut accepter un paiement de ce montant"""
        return montant <= self.montant_restant and montant > 0


class TranchePaiementKt(models.Model):
    """Modèle pour chaque tranche de paiement individuelle"""

    # Relation avec le paiement principal
    paiement_especes = models.ForeignKey(
        PaiementEspecesKt,
        on_delete=models.CASCADE,
        related_name="tranches",
        verbose_name="Paiement principal",
    )

    # Détails du paiement
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant de cette tranche",
    )

    # Dates
    date_paiement = models.DateTimeField(
        default=timezone.now, verbose_name="Date du paiement"
    )

    # Traçabilité
    encaisse_par = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="tranches_encaissees",
        verbose_name="Encaissé par",
    )

    notes = models.TextField(blank=True, verbose_name="Notes sur cette tranche")

    class Meta:
        verbose_name = "Tranche de paiement"
        verbose_name_plural = "Tranches de paiement"
        ordering = ["-date_paiement"]
        indexes = [
            models.Index(fields=["paiement_especes"]),
            models.Index(fields=["date_paiement"]),
            models.Index(fields=["encaisse_par"]),
        ]
        permissions = (
            ("annuler_tranche_paiement", "Peut annuler une tranche de paiement"),
            ("modifier_tranche_paiement", "Peut modifier une tranche de paiement"),
            ("view_details_tranche", "Peut voir les détails d'une tranche"),
        )

    def __str__(self):
        return f"Tranche #{self.id} - {self.montant} DA {self.date_paiement.strftime('%d/%m/%Y %H:%M')}"

    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)

        # Mettre à jour le paiement principal
        self._update_paiement_principal()

    def delete(self, *args, **kwargs):
        paiement_especes = self.paiement_especes
        super().delete(*args, **kwargs)
        # Mettre à jour le paiement principal après suppression
        paiement_especes._recalculate_and_update()

    def _update_paiement_principal(self):
        """Met à jour les montants du paiement principal"""
        paiement = self.paiement_especes
        paiement._recalculate_and_update()
