# pharmacies/models/approvisionnement_interne.py

import uuid
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Sum, Q
from django.utils import timezone
from ..models.produit import Produit
from medical.models.services import Service

from .stock import MouvementStock, Stock

User = get_user_model()


class DemandeInterne(models.Model):
    """
    Représente une demande d'approvisionnement d'un service vers la pharmacie
    """

    STATUT_CHOICES = [
        ("EN_ATTENTE", "En attente"),
        ("VALIDEE", "Validée"),
        ("PREPAREE", "Préparée"),
        ("LIVREE", "Livrée"),
        ("REJETEE", "Rejetée"),
        ("ANNULEE", "Annulée"),
    ]

    PRIORITE_CHOICES = [
        ("NORMALE", "Normale"),
        ("URGENTE", "Urgente"),
        ("CRITIQUE", "Critique"),
    ]

    # Identifiant unique
    reference = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        help_text="Référence unique de la demande",
    )

    # Services impliqués
    service_demandeur = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="demandes_internes_emises",
        help_text="Service qui émet la demande",
    )

    pharmacie = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="demandes_internes_recues",
        limit_choices_to={"type_service": "PHARMACIE"},
        help_text="Pharmacie qui traite la demande",
    )

    # Informations temporelles
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_preparation = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)

    # Statut et priorité
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="EN_ATTENTE"
    )

    priorite = models.CharField(
        max_length=20, choices=PRIORITE_CHOICES, default="NORMALE"
    )

    # Utilisateurs impliqués
    creee_par = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="demandes_internes_creees"
    )

    validee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_internes_validees",
    )

    preparee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_internes_preparees",
    )

    livree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_internes_livrees",
    )

    # Observations et notes
    motif_demande = models.TextField(
        blank=True, help_text="Motif ou justification de la demande"
    )

    observations = models.TextField(blank=True, help_text="Observations générales")

    motif_rejet = models.TextField(blank=True, help_text="Motif du rejet si applicable")

    class Meta:
        verbose_name = "Demande interne"
        verbose_name_plural = "Demandes internes"
        ordering = ["-date_creation"]
        permissions = [
            ("can_validate_demande_interne", "Peut valider les demandes internes"),
            ("can_prepare_demande_interne", "Peut préparer les demandes internes"),
            ("can_deliver_demande_interne", "Peut livrer les demandes internes"),
        ]

    def __str__(self):
        return f"DI-{self.reference} - {self.service_demandeur.nom}"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Générer une référence unique
            self.reference = self.generate_reference()
        super().save(*args, **kwargs)

    def generate_reference(self):
        """Génère une référence unique pour la demande"""
        prefix = "DI"
        year = timezone.now().year
        month = timezone.now().month

        # Compter les demandes du mois
        count = (
            DemandeInterne.objects.filter(
                date_creation__year=year, date_creation__month=month
            ).count()
            + 1
        )

        return f"{prefix}-{year}{month:02d}-{count:04d}"

    @property
    def total_produits(self):
        """Nombre total de produits différents"""
        return self.lignes.count()

    @property
    def total_quantite(self):
        """Quantité totale demandée"""
        return self.lignes.aggregate(total=Sum("quantite_demandee"))["total"] or 0

    @property
    def total_quantite_accordee(self):
        """Quantité totale accordée"""
        return self.lignes.aggregate(total=Sum("quantite_accordee"))["total"] or 0

    @property
    def est_urgente(self):
        """Vérifie si la demande est urgente ou critique"""
        return self.priorite in ["URGENTE", "CRITIQUE"]

    @property
    def peut_etre_validee(self):
        """Vérifie si la demande peut être validée"""
        return self.statut == "EN_ATTENTE"

    @property
    def peut_etre_preparee(self):
        """Vérifie si la demande peut être préparée"""
        return self.statut == "VALIDEE"

    @property
    def peut_etre_livree(self):
        """Vérifie si la demande peut être livrée"""
        return self.statut == "PREPAREE"

    def valider(self, user, lignes_data=None):
        """Valide la demande et met à jour les quantités accordées"""
        if not self.peut_etre_validee:
            raise ValidationError("Cette demande ne peut pas être validée")

        with transaction.atomic():
            self.statut = "VALIDEE"
            self.date_validation = timezone.now()
            self.validee_par = user
            self.save()

            # Mettre à jour les quantités accordées si fournies
            if lignes_data:
                for ligne_data in lignes_data:
                    ligne = self.lignes.get(id=ligne_data["id"])
                    ligne.quantite_accordee = ligne_data.get(
                        "quantite_accordee", ligne.quantite_demandee
                    )
                    ligne.save()

    def rejeter(self, user, motif=""):
        """Rejette la demande"""
        if not self.peut_etre_validee:
            raise ValidationError("Cette demande ne peut pas être rejetée")

        self.statut = "REJETEE"
        self.date_validation = timezone.now()
        self.validee_par = user
        self.motif_rejet = motif
        self.save()

    def preparer(self, user):
        """Prépare la demande et vérifie les stocks"""
        if not self.peut_etre_preparee:
            raise ValidationError("Cette demande ne peut pas être préparée")

        # Vérifier la disponibilité des stocks
        with transaction.atomic():
            for ligne in self.lignes.all():
                stock_disponible = Stock.objects.get_stock_disponible(
                    produit=ligne.produit, service=self.pharmacie
                )

                quantite_a_servir = ligne.quantite_accordee or ligne.quantite_demandee

                if stock_disponible < quantite_a_servir:
                    raise ValidationError(
                        f"Stock insuffisant pour {ligne.produit.nom}. "
                        f"Disponible: {stock_disponible}, Demandé: {quantite_a_servir}"
                    )

            self.statut = "PREPAREE"
            self.date_preparation = timezone.now()
            self.preparee_par = user
            self.save()

    def livrer(self, user):
        """Livre la demande et met à jour les stocks"""
        if not self.peut_etre_livree:
            raise ValidationError("Cette demande ne peut pas être livrée")

        with transaction.atomic():
            for ligne in self.lignes.all():
                quantite_livree = ligne.quantite_accordee or ligne.quantite_demandee

                # Créer le mouvement de stock (sortie de la pharmacie)
                MouvementStock.objects.create(
                    produit=ligne.produit,
                    service=self.pharmacie,
                    type_mouvement="SORTIE",
                    quantite=quantite_livree,
                    motif=f"Livraison demande interne {self.reference}",
                    reference_document=self.reference,
                    effectue_par=user,
                )

                # Créer le mouvement de stock (entrée dans le service)
                MouvementStock.objects.create(
                    produit=ligne.produit,
                    service=self.service_demandeur,
                    type_mouvement="ENTREE",
                    quantite=quantite_livree,
                    motif=f"Réception demande interne {self.reference}",
                    reference_document=self.reference,
                    effectue_par=user,
                )

                # Mettre à jour la quantité livrée
                ligne.quantite_livree = quantite_livree
                ligne.save()

            self.statut = "LIVREE"
            self.date_livraison = timezone.now()
            self.livree_par = user
            self.save()

    def annuler(self, user, motif=""):
        """Annule la demande"""
        if self.statut in ["LIVREE", "ANNULEE"]:
            raise ValidationError("Cette demande ne peut pas être annulée")

        self.statut = "ANNULEE"
        self.observations = f"Annulée par {user.get_full_name()}: {motif}"
        self.save()


class LigneDemandeInterne(models.Model):
    """
    Ligne de détail d'une demande interne
    """

    demande = models.ForeignKey(
        DemandeInterne, on_delete=models.CASCADE, related_name="lignes"
    )

    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)

    quantite_demandee = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], help_text="Quantité demandée par le service"
    )

    quantite_accordee = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Quantité accordée par la pharmacie",
    )

    quantite_livree = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Quantité effectivement livrée",
    )

    observations = models.TextField(
        blank=True, help_text="Observations sur cette ligne"
    )

    class Meta:
        verbose_name = "Ligne de demande interne"
        verbose_name_plural = "Lignes de demande interne"
        unique_together = [["demande", "produit"]]

    def __str__(self):
        return f"{self.produit.nom} - Qté: {self.quantite_demandee}"

    @property
    def stock_disponible_pharmacie(self):
        """Retourne le stock disponible dans la pharmacie"""
        return Stock.objects.get_stock_disponible(
            produit=self.produit, service=self.demande.pharmacie
        )

    @property
    def est_stock_suffisant(self):
        """Vérifie si le stock est suffisant pour cette ligne"""
        quantite_necessaire = self.quantite_accordee or self.quantite_demandee
        return self.stock_disponible_pharmacie >= quantite_necessaire
