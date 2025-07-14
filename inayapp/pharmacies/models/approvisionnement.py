# pharmacies/models/approvisionnement.py
import uuid
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Sum
from django.utils import timezone
from medical.models.services import Service

from .stock import MouvementStock, Stock
from django.db import models
from django.contrib.auth.models import User

User = get_user_model()


class ExpressionBesoin(models.Model):
    TYPE_APPROVISIONNEMENT_CHOICES = [
        ("EXTERNE", "Approvisionnement externe (fournisseur)"),
        ("INTERNE", "Approvisionnement interne (pharmacie)"),
    ]

    STATUT_CHOICES = [
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validée"),
        ("REJETE", "Rejetée"),
        ("SERVIE", "Servie"),
    ]
    PRIORITE_CHOICES = [
        ("NORMALE", "Normale"),
        ("URGENTE", "Urgente"),
        ("CRITIQUE", "Critique"),
    ]
    reference = models.CharField(max_length=100, unique=True, blank=True)
    type_approvisionnement = models.CharField(
        max_length=20,
        choices=TYPE_APPROVISIONNEMENT_CHOICES,
        default="EXTERNE",
        help_text="Type d'approvisionnement demandé",
    )
    service_demandeur = models.ForeignKey(
        "medical.Service", on_delete=models.PROTECT, related_name="besoins_emmis"
    )
    service_approvisionneur = models.ForeignKey(
        "medical.Service",
        on_delete=models.PROTECT,
        related_name="besoins_recus",
        null=True,
        blank=True,
        help_text="Service qui traite la demande (pharmacie pour externe, pharmacie pour interne)",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="EN_ATTENTE"
    )
    valide_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="besoins_valides",
    )
    priorite = models.CharField(
        max_length=20,
        choices=PRIORITE_CHOICES,
        default="NORMALE",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="expressions_besoin_creees"
    )
    class Meta:
        verbose_name = "Expression de besoin"
        verbose_name_plural = "Expressions de besoin"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Générer la référence au format : EB-ANNÉE-SERVICE-USER
            year = datetime.now().year

            # Obtenir le code du service (3-4 premières lettres en majuscules)
            service_code = self.service_demandeur.name[:6].upper().replace(" ", "")

            # Obtenir le nom de l'utilisateur (prénom ou username)
            user_code = (
                self.created_by.first_name[:6].upper()
                if self.created_by.first_name
                else self.created_by.username[:6].upper()
            )

            # Compter le nombre d'expressions de besoin pour ce service cette année
            count = (
                ExpressionBesoin.objects.filter(
                    date_creation__year=year, service_demandeur=self.service_demandeur
                ).count()
                + 1
            )

            # Générer la référence
            self.reference = f"EB-{count:03d}-{year}-{service_code}-{user_code}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference}"

    def valider(self, user):
        if self.statut != "EN_ATTENTE":
            raise ValidationError("Seuls les besoins en attente peuvent être validés")

        self.statut = "VALIDE"
        self.date_validation = timezone.now()
        self.valide_par = user
        self.save()

    @property
    def total_articles(self):
        return self.lignes.aggregate(total=Sum("quantite_demandee"))["total"] or 0

    @property
    def est_approvisionnement_interne(self):
        return self.type_approvisionnement == "INTERNE"


# Nouveau modèle pour les demandes internes
class DemandeInterne(models.Model):
    STATUT_CHOICES = [
        ("EN_ATTENTE", "En attente"),
        ("VALIDEE", "Validée"),
        ("PREPAREE", "Préparée"),
        ("LIVREE", "Livrée"),
        ("REJETEE", "Rejetée"),
    ]

    reference = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    besoin = models.OneToOneField(
        ExpressionBesoin,
        on_delete=models.PROTECT,
        related_name="demande_interne",
        limit_choices_to={"type_approvisionnement": "INTERNE"},
    )
    service_destinataire = models.ForeignKey(
        "medical.Service", on_delete=models.PROTECT, related_name="demandes_recues"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_preparation = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="EN_ATTENTE"
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
    observations = models.TextField(blank=True)

    class Meta:
        verbose_name = "Demande interne"
        verbose_name_plural = "Demandes internes"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"DI-{self.reference}"

    def valider(self, user):
        if self.statut != "EN_ATTENTE":
            raise ValidationError(
                "Seules les demandes en attente peuvent être validées"
            )

        self.statut = "VALIDEE"
        self.date_validation = timezone.now()
        self.validee_par = user
        self.save()

    def preparer(self, user):
        if self.statut != "VALIDEE":
            raise ValidationError("Seules les demandes validées peuvent être préparées")

        # Vérifier la disponibilité des produits en stock
        service_pharmacie = self.besoin.service_approvisionneur

        with transaction.atomic():
            for ligne in self.lignes.all():
                stock_disponible = Stock.objects.get_stock_disponible(
                    produit=ligne.produit, service=service_pharmacie
                )

                if stock_disponible < ligne.quantite_accordee:
                    raise ValidationError(
                        f"Stock insuffisant pour {ligne.produit.nom}. "
                        f"Disponible: {stock_disponible}, Demandé: {ligne.quantite_accordee}"
                    )

            self.statut = "PREPAREE"
            self.date_preparation = timezone.now()
            self.preparee_par = user
            self.save()

    def livrer(self, user):
        if self.statut != "PREPAREE":
            raise ValidationError("Seules les demandes préparées peuvent être livrées")

        service_pharmacie = self.besoin.service_approvisionneur
        service_destinataire = self.service_destinataire

        with transaction.atomic():
            for ligne in self.lignes.all():
                # Sortie du stock pharmacie
                Stock.objects.sortir_stock(
                    produit=ligne.produit,
                    service=service_pharmacie,
                    quantite=ligne.quantite_accordee,
                )

                # Entrée dans le stock du service destinataire (si géré)
                if service_destinataire.gere_stock:
                    Stock.objects.entrer_stock(
                        produit=ligne.produit,
                        service=service_destinataire,
                        quantite=ligne.quantite_accordee,
                    )

                # Enregistrer les mouvements
                MouvementStock.log_mouvement(
                    instance=self,
                    type_mouvement="SORTIE",
                    produit=ligne.produit,
                    service=service_pharmacie,
                    quantite=ligne.quantite_accordee,
                    observations=f"Livraison vers {service_destinataire.name}",
                )

                if service_destinataire.gere_stock:
                    MouvementStock.log_mouvement(
                        instance=self,
                        type_mouvement="ENTREE",
                        produit=ligne.produit,
                        service=service_destinataire,
                        quantite=ligne.quantite_accordee,
                        observations=f"Réception de la pharmacie",
                    )

            self.statut = "LIVREE"
            self.date_livraison = timezone.now()
            self.livree_par = user
            self.save()

            # Marquer le besoin comme servi
            self.besoin.statut = "SERVIE"
            self.besoin.save()


class LigneDemandeInterne(models.Model):
    demande = models.ForeignKey(
        DemandeInterne, on_delete=models.PROTECT, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite_demandee = models.PositiveIntegerField()
    quantite_accordee = models.PositiveIntegerField(null=True, blank=True)
    observations = models.TextField(blank=True)

    class Meta:
        verbose_name = "Ligne de demande interne"
        verbose_name_plural = "Lignes de demande interne"
        unique_together = ("demande", "produit")

    def __str__(self):
        return f"{self.produit} - {self.quantite_demandee}"


class LigneBesoin(models.Model):
    besoin = models.ForeignKey(
        ExpressionBesoin, on_delete=models.PROTECT, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite_demandee = models.PositiveIntegerField()
    quantite_validee = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Ligne de besoin"
        verbose_name_plural = "Lignes de besoin"
        unique_together = ("besoin", "produit")

    def __str__(self):
        return f"{self.produit} - {self.quantite_demandee}"


class CommandeFournisseur(models.Model):
    STATUT_CHOICES = [
        ("BROUILLON", "Brouillon"),
        ("EN_ATTENTE", "En attente"),
        ("CONFIRME", "Confirmée"),
        ("ANNULE", "Annulée"),
        ("LIVREE", "Livrée"),
    ]

    reference = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    besoin = models.ForeignKey(
        ExpressionBesoin,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes",
        limit_choices_to={"type_approvisionnement": "EXTERNE"},  # Ajout de cette limite
    )
    fournisseur = models.ForeignKey("Fournisseur", on_delete=models.PROTECT)
    date_commande = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="BROUILLON"
    )
    valide_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_validees",
    )

    class Meta:
        verbose_name = "Commande fournisseur"
        verbose_name_plural = "Commandes fournisseurs"
        ordering = ["-date_commande"]

    def __str__(self):
        return f"CMD-{self.reference}"

    def confirmer(self, user):
        if self.statut != "BROUILLON":
            raise ValidationError(
                "Seules les commandes brouillon peuvent être confirmées"
            )

        self.statut = "EN_ATTENTE"
        self.date_confirmation = timezone.now()
        self.valide_par = user
        self.save()

    @property
    def montant_total(self):
        return self.lignes.aggregate(
            total=Sum(F("quantite_commandee") * F("prix_unitaire"))
        )["total"] or Decimal("0.00")


class LigneCommande(models.Model):
    commande = models.ForeignKey(
        CommandeFournisseur, on_delete=models.PROTECT, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite_commandee = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"
        unique_together = ("commande", "produit")

    def __str__(self):
        return f"{self.produit} - {self.quantite_commandee} x {self.prix_unitaire}"


class Livraison(models.Model):
    STATUT_CHOICES = [
        ("EN_TRANSIT", "En transit"),
        ("RECU", "Reçu"),
        ("PARTIEL", "Reçu partiellement"),
        ("ANNULE", "Annulé"),
    ]

    reference = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    commande = models.ForeignKey(
        CommandeFournisseur, on_delete=models.PROTECT, related_name="livraisons"
    )
    date_livraison_prevue = models.DateField()
    date_reception = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="EN_TRANSIT"
    )
    recepteur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="livraisons_recues",
    )

    class Meta:
        verbose_name = "Livraison"
        verbose_name_plural = "Livraisons"
        ordering = ["-date_livraison_prevue"]

    def __str__(self):
        return f"LIV-{self.reference}"

    def recevoir(self, user):
        if self.statut not in ["EN_TRANSIT", "PARTIEL"]:
            raise ValidationError(
                "Seules les livraisons en transit peuvent être reçues"
            )

        # Mise à jour du stock
        service_pharmacie = Service.objects.get(est_pharmacies=True)

        for ligne in self.lignes.all():
            Stock.objects.update_or_create_stock(
                produit=ligne.produit,
                service=service_pharmacie,
                date_peremption=ligne.date_peremption,
                numero_lot=ligne.numero_lot,
                quantite=ligne.quantite_livree,
            )

            MouvementStock.log_mouvement(
                instance=self,
                type_mouvement="ENTREE",
                produit=ligne.produit,
                service=service_pharmacie,
                quantite=ligne.quantite_livree,
                lot_concerne=ligne.numero_lot,
            )

        self.statut = "RECU"
        self.date_reception = timezone.now()
        self.recepteur = user
        self.save()

        # Générer le bon de réception
        BonReception.objects.create(livraison=self)


class LigneLivraison(models.Model):
    livraison = models.ForeignKey(
        Livraison, on_delete=models.PROTECT, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite_livree = models.PositiveIntegerField()
    numero_lot = models.CharField(max_length=50)
    date_peremption = models.DateField()

    class Meta:
        verbose_name = "Ligne de livraison"
        verbose_name_plural = "Lignes de livraison"
        unique_together = ("livraison", "produit", "numero_lot")

    def __str__(self):
        return f"{self.produit} - Lot: {self.numero_lot}"


class BonReception(models.Model):
    reference = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    livraison = models.OneToOneField(
        Livraison, on_delete=models.PROTECT, related_name="bon_reception"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    controleur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bons_reception",
    )

    class Meta:
        verbose_name = "Bon de réception"
        verbose_name_plural = "Bons de réception"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"BR-{self.reference}"

    @property
    def details_livraison(self):
        return self.livraison.lignes.all()
