# medical/models/services.py

from django.db import models
from django.utils import timezone
from decimal import Decimal
from django.core.validators import MinValueValidator


class Service(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    est_stockeur = models.BooleanField(default=False)
    est_pharmacies = models.BooleanField(default=False)
    est_hospitalier = models.BooleanField(default=False, verbose_name="Service hospitalier")
    est_active = models.BooleanField(default=True)

    # NOUVEAUX CHAMPS pour la facturation des séjours courts
    tarif_fixe_sejour_court = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("7000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Tarif fixe séjour court (DA)",
        help_text="Montant fixe facturé pour les séjours de moins de 24h dans ce service"
    )

    seuil_sejour_court_heures = models.PositiveSmallIntegerField(
        default=24,
        verbose_name="Seuil séjour court (heures)",
        help_text="Durée en heures en dessous de laquelle le tarif fixe s'applique (défaut: 24h)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name

    @property
    def total_beds(self):
        # Somme des capacités déclarées des chambres actives
        return sum(
            c.capacite_lits for c in self.chambres.filter(est_active=True)
        )

    @property
    def occupied_beds(self):
        # Somme des lits occupés (via propriété calculée de Chambre/Lit)
        return sum(
            c.nombre_lits_occupes for c in self.chambres.filter(est_active=True)
        )

    @property
    def available_beds(self):
        return max(0, self.total_beds - self.occupied_beds)

    @property
    def occupancy_rate(self):
        total = self.total_beds
        if total == 0:
            return 0
        return round((self.occupied_beds / total) * 100, 1)

    def calculer_cout_sejour_court(self, prix_nuit_chambre: Decimal, duree_heures: int) -> Decimal:
        """
        Calcule le coût pour un séjour court selon la formule :
        tarif_fixe + ((prix_nuit - tarif_fixe) / 24h) * duree_heures

        Args:
            prix_nuit_chambre: Prix normal de la nuitée de la chambre
            duree_heures: Durée du séjour en heures

        Returns:
            Coût calculé pour le séjour court
        """
        if duree_heures >= self.seuil_sejour_court_heures:
            # Séjour normal - facturation à la nuitée complète
            return prix_nuit_chambre

        # Séjour court - application de la formule
        tarif_variable = prix_nuit_chambre - self.tarif_fixe_sejour_court
        cout_variable = (tarif_variable / Decimal(str(self.seuil_sejour_court_heures))) * Decimal(str(duree_heures))

        return self.tarif_fixe_sejour_court + cout_variable

    def get_description_tarification(self) -> str:
        """Retourne une description de la tarification pour ce service"""
        return (
            f"Séjour < {self.seuil_sejour_court_heures}h: "
            f"{self.tarif_fixe_sejour_court} DA + tarif horaire variable"
        )