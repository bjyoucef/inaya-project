# pharmacies/models/produit.py
from django.db import models
from django.urls import reverse
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class ProduitManager(models.Manager):
    """Manager personnalisé pour le modèle Produit"""

    def actifs(self):
        """Retourne tous les produits actifs"""
        return self.filter(est_actif=True)

    def medicaments(self):
        """Retourne tous les médicaments"""
        return self.filter(type_produit="MED")

    def consommables(self):
        """Retourne tous les consommables"""
        return self.filter(type_produit="CONS")

    def avec_marge_beneficiaire(self):
        """Retourne les produits avec leur marge bénéficiaire calculée"""
        return self.annotate(
            marge_calculee=models.F("prix_vente") - models.F("prix_achat"),
            pourcentage_marge_calculee=models.Case(
                models.When(
                    prix_achat__gt=0,
                    then=(models.F("prix_vente") - models.F("prix_achat"))
                    / models.F("prix_achat")
                    * 100,
                ),
                default=0,
                output_field=models.DecimalField(),
            ),
        )


class Produit(models.Model):
    """Modèle représentant un produit de pharmacie"""

    class TypeProduit(models.TextChoices):
        MEDICAMENT = "MED", "Médicament"
        CONSOMMABLE = "CONS", "Consommable"

    # Informations de base
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom du produit",
        help_text="Nom commercial du produit",
    )
    code_produit = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Code produit",
        help_text="Code interne unique du produit",
    )
    code_barres = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Code-barres",
        help_text="Code-barres EAN du produit",
    )

    # Classification
    type_produit = models.CharField(
        max_length=4, choices=TypeProduit.choices, verbose_name="Type de produit"
    )

    # Prix et coûts
    prix_achat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix d'achat (€)",
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Prix d'achat hors taxes",
    )
    prix_vente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix de vente (€)",
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Prix de vente TTC",
    )

    # Informations supplémentaires
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description",
        help_text="Description détaillée du produit",
    )

    # Statut et dates
    est_actif = models.BooleanField(
        default=True,
        verbose_name="Produit actif",
        help_text="Décochez pour désactiver le produit",
    )
    date_creation = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True, verbose_name="Dernière modification"
    )

    # Manager personnalisé
    objects = ProduitManager()

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["nom"]
        indexes = [
            models.Index(fields=["code_produit"]),
            models.Index(fields=["type_produit"]),
            models.Index(fields=["est_actif"]),
            models.Index(fields=["-date_creation"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(prix_achat__gte=0), name="prix_achat_positif"
            ),
            models.CheckConstraint(
                check=models.Q(prix_vente__gte=0), name="prix_vente_positif"
            ),
        ]

    def __str__(self):
        return f"{self.code_produit} - {self.nom}"

    def get_absolute_url(self):
        """Retourne l'URL de détail du produit"""
        return reverse("pharmacies:produit_detail", kwargs={"pk": self.pk})

    @property
    def marge_beneficiaire(self):
        """Calcule la marge bénéficiaire en euros"""
        return self.prix_vente - self.prix_achat

    @property
    def pourcentage_marge(self):
        """Calcule le pourcentage de marge bénéficiaire"""
        if self.prix_achat > 0:
            return ((self.prix_vente - self.prix_achat) / self.prix_achat) * 100
        return 0

    @property
    def est_rentable(self):
        """Vérifie si le produit est rentable"""
        return self.prix_vente > self.prix_achat

    def clean(self):
        """Validation personnalisée"""
        from django.core.exceptions import ValidationError

        super().clean()

        if self.prix_vente and self.prix_achat and self.prix_vente < self.prix_achat:
            raise ValidationError(
                {
                    "prix_vente": "Le prix de vente ne peut pas être inférieur au prix d'achat."
                }
            )

    def save(self, *args, **kwargs):
        """Sauvegarde avec validation"""
        self.full_clean()
        super().save(*args, **kwargs)


# pharmacies/models/fournisseur.py

from decimal import Decimal
from django.db.models import F
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.forms import ValidationError
from django.utils import timezone


class Fournisseur(models.Model):
    TYPE_PAIEMENT_CHOICES = [
        ("VIREMENT", "Virement bancaire"),
        ("CHEQUE", "Chèque"),
        ("ESPECES", "Espèces"),
        ("CREDIT", "Crédit"),
    ]

    STATUT_CHOICES = [
        ("ACTIF", "Actif"),
        ("SUSPENDU", "Suspendu"),
        ("ARCHIVE", "Archivé"),
    ]

    FORMES_JURIDIQUES = [
        ("SARL", "SARL"),
        ("EURL", "EURL"),
        ("SNC", "SNC"),
        ("ETS", "ETS"),
        ("AUTRE", "Autre"),
    ]

    code_fournisseur = models.CharField(
        "Code unique",
        max_length=20,
        unique=True,
        help_text="Identifiant unique du fournisseur",
    )
    raison_sociale = models.CharField("Raison sociale", max_length=255, unique=True)
    forme_juridique = models.CharField(
        max_length=50, choices=FORMES_JURIDIQUES, default="SARL"
    )
    domaine_activite = models.CharField("Domaine d'activité", max_length=100)
    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20)
    adresse = models.TextField()
    ville = models.CharField(max_length=100)
    pays = models.CharField(max_length=100, default="Algérie")
    conditions_paiement = models.PositiveIntegerField(
        "Délai de paiement (jours)",
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(365)],
    )
    limite_credit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    solde = models.DecimalField(
        "Solde actuel", max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    mode_paiement_prefere = models.CharField(
        max_length=50, choices=TYPE_PAIEMENT_CHOICES, default="VIREMENT"
    )
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default="ACTIF")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        constraints = [
            models.UniqueConstraint(
                fields=["code_fournisseur", "raison_sociale"], name="unique_fournisseur"
            )
        ]

    def __str__(self):
        return f"{self.code_fournisseur} - {self.raison_sociale}"

    @property
    def credit_disponible(self):
        return self.limite_credit - self.solde

    def mettre_a_jour_solde(self, montant, operation="ajout"):
        with transaction.atomic():
            if operation == "ajout":
                Fournisseur.objects.filter(pk=self.pk).update(
                    solde=F("solde") + montant
                )
            elif operation == "retrait":
                Fournisseur.objects.filter(pk=self.pk).update(
                    solde=F("solde") - montant
                )
            self.refresh_from_db()

    def clean(self):
        if self.limite_credit < 0:
            raise ValidationError(
                {"limite_credit": "La limite de crédit ne peut pas être négative"}
            )

        if self.conditions_paiement > 365:
            raise ValidationError(
                {"conditions_paiement": "Le délai ne peut excéder 365 jours"}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class HistoriquePaiement(models.Model):
    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.CASCADE, related_name="historique_paiements"
    )
    achat = models.ForeignKey(
        "pharmacies.Achat", on_delete=models.SET_NULL, null=True, blank=True
    )
    date_paiement = models.DateTimeField(default=timezone.now)
    montant = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    mode_paiement = models.CharField(
        max_length=50, choices=Fournisseur.TYPE_PAIEMENT_CHOICES
    )
    reference = models.CharField("Référence transaction", max_length=100, blank=True)
    statut = models.CharField(
        max_length=50,
        choices=[
            ("EN_ATTENTE", "En attente"),
            ("COMPLETE", "Complété"),
            ("ANNULE", "Annulé"),
        ],
        default="EN_ATTENTE",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_paiement"]
        verbose_name = "Historique de paiement"
        verbose_name_plural = "Historiques de paiement"

    def __str__(self):
        return f"Paiement {self.montant}€ - {self.fournisseur}"

    def save(self, *args, **kwargs):
        if self.statut == "COMPLETE" and not self.reference:
            self.reference = f"PAY-{self.date_paiement.strftime('%Y%m%d')}-{self.id}"
        super().save(*args, **kwargs)
        if self.statut == "COMPLETE":
            self.fournisseur.mettre_a_jour_solde(self.montant, operation="retrait")


class OrdrePaiement(models.Model):
    MODES_PAIEMENT = [
        ("VIREMENT", "Virement bancaire"),
        ("CHEQUE", "Chèque"),
        ("ESPECES", "Espèces"),
    ]

    commande = models.ForeignKey(
        "BonCommande", on_delete=models.PROTECT, related_name="paiements"
    )
    reference = models.CharField(max_length=50, unique=True)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODES_PAIEMENT)
    date_paiement = models.DateField()
    preuve = models.FileField(upload_to="paiements/", blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PAY-{self.date_paiement.strftime('%Y%m%d')}-{self.id}"
        super().save(*args, **kwargs)
        self.commande.fournisseur.mettre_a_jour_solde(self.montant, operation="retrait")


# pharmacies/models/commande.py

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from ..models import MouvementStock, Stock


class Achat(models.Model):
    livraison = models.ForeignKey(
        "BonLivraison", on_delete=models.SET_NULL, null=True, related_name="achats"
    )
    service_destination = models.ForeignKey(
        "medical.Service", on_delete=models.PROTECT, verbose_name="Service destinataire"
    )
    produit = models.ForeignKey(
        "Produit", on_delete=models.PROTECT, verbose_name="Produit"
    )
    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.PROTECT,
        verbose_name="Fournisseur",
    )

    quantite_achetee = models.PositiveIntegerField(verbose_name="Quantité achetée")
    prix_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Prix unitaire"
    )
    date_achat = models.DateTimeField(auto_now_add=True, verbose_name="Date d'achat")
    numero_lot = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Numéro de lot"
    )
    date_peremption = models.DateTimeField(verbose_name="Date de péremption")

    class Meta:
        verbose_name = "Achat"
        verbose_name_plural = "Achats"

    def __str__(self):
        return f"Achat {self.produit} - {self.fournisseur}"

    def get_absolute_url(self):
        return reverse("pharmacies:achat_detail", kwargs={"pk": self.pk})

    @property
    def montant_total(self):
        return self.quantite_achetee * self.prix_unitaire

    def save(self, *args, **kwargs):
        if not self.service_destination:
            raise ValidationError("Le service destinataire est obligatoire")

        # Corriger la comparaison de dates
        if self.date_peremption.date() < timezone.now().date():
            raise ValidationError(
                "La date de péremption ne peut pas être dans le passé"
            )

        is_new = not self.pk
        super().save(*args, **kwargs)

        if is_new:
            # Utilisation de la nouvelle méthode du manager
            stock = Stock.objects.update_or_create_stock(
                produit=self.produit,
                service=self.service_destination,
                date_peremption=self.date_peremption.date(),
                numero_lot=self.numero_lot,
                quantite=self.quantite_achetee,
            )

            MouvementStock.log_mouvement(
                instance=self,
                type_mouvement="ENTREE",
                produit=self.produit,
                service=self.service_destination,
                quantite=self.quantite_achetee,
                lot_concerne=self.numero_lot,
            )


class BonCommande(models.Model):
    STATUT_CHOICES = [
        ("BROUILLON", "Brouillon"),
        ("VALIDE", "Validé"),
        ("LIVRE", "Livré"),
        ("FACTURE", "Facturé"),
        ("ANNULE", "Annulé"),
    ]

    fournisseur = models.ForeignKey(
        "Fournisseur", on_delete=models.PROTECT, related_name="commandes"
    )
    numero_commande = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    date_commande = models.DateTimeField(auto_now_add=True)
    date_livraison_prevue = models.DateTimeField()
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="BROUILLON"
    )
    commentaire = models.TextField(blank=True)
    service_destination = models.ForeignKey("medical.Service", on_delete=models.PROTECT)

    def generate_numero(self):
        return f"CMD-{self.date_commande.strftime('%Y%m%d')}-{str(self.id).zfill(5)}"

    def save(self, *args, **kwargs):
        if not self.numero_commande:
            self.numero_commande = self.generate_numero()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date_commande"]
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"

    def __str__(self):
        return f"CMD-{self.numero_commande}"

    @property
    def montant_total(self):
        return sum(ligne.montant for ligne in self.lignes.all())

    def get_absolute_url(self):
        return reverse("pharmacies:commande_detail", kwargs={"pk": self.pk})


class LigneCommande(models.Model):
    commande = models.ForeignKey(
        BonCommande, on_delete=models.CASCADE, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    date_peremption = models.DateTimeField()
    numero_lot = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    @property
    def montant(self):
        return self.quantite * self.prix_unitaire


# pharmacies/models/commande.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid
from django.db import models, transaction


class BonLivraison(models.Model):
    commande = models.ForeignKey(
        BonCommande,
        on_delete=models.PROTECT,
        related_name="livraisons",
        verbose_name="Commande associée",
    )
    numero_bl = models.CharField(max_length=50, unique=True, verbose_name="Numéro BL")
    date_livraison = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de livraison"
    )
    fichier_bl = models.FileField(
        upload_to="bl/%Y/%m/%d/", verbose_name="Fichier BL", blank=True
    )
    est_complet = models.BooleanField(default=False, verbose_name="Livraison complète")
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, null=True, verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Bon de livraison"
        verbose_name_plural = "Bons de livraison"
        ordering = ["-date_livraison"]

    def __str__(self):
        return f"BL {self.numero_bl} - {self.commande.numero_commande}"

    def clean(self):
        if not hasattr(self, "commande") or self.commande.statut not in [
            "VALIDE",
            "LIVRE",
        ]:
            raise ValidationError("La commande doit être validée avant livraison")

    def save(self, *args, **kwargs):
        if not self.numero_bl:
            self.numero_bl = self.generate_numero_bl()
        super().save(*args, **kwargs)

    def generate_numero_bl(self):
        return f"BL-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    @transaction.atomic
    def mettre_a_jour_stock(self):
        if self.est_complet:
            return

        for ligne in self.commande.lignes.all():
            achat, created = Achat.objects.get_or_create(
                livraison=self,
                produit=ligne.produit,
                defaults={
                    "service_destination": self.commande.service_destination,
                    "fournisseur": self.commande.fournisseur,
                    "quantite_achetee": ligne.quantite,
                    "prix_unitaire": ligne.prix_unitaire,
                    "date_peremption": ligne.date_peremption,
                    "numero_lot": ligne.numero_lot,
                },
            )

            if created:
                MouvementStock.log_mouvement(
                    instance=self,
                    type_mouvement="ENTREE",
                    produit=ligne.produit,
                    service=self.commande.service_destination,
                    quantite=ligne.quantite,
                    lot_concerne=ligne.numero_lot,
                )

        self.est_complet = True
        self.save(update_fields=["est_complet"])
        self.commande.statut = "LIVRE"
        self.commande.save(update_fields=["statut"])


from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class DemandeInterne(models.Model):
    STATUT_CHOICES = [
        ("BROUILLON", "Brouillon"),
        ("EN_ATTENTE", "En attente"),
        ("APPROUVE", "Approuvé"),
        ("REFUSE", "Refusé"),
        ("LIVRE", "Livre"),
    ]

    service_demandeur = models.ForeignKey(
        "medical.Service", on_delete=models.PROTECT, related_name="demandes_internes"
    )
    produit = models.ForeignKey("pharmacies.Produit", on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField()
    date_demande = models.DateTimeField(auto_now_add=True)
    date_besoin = models.DateField()
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="BROUILLON"
    )
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "Demande interne"
        verbose_name_plural = "Demandes internes"

    def __str__(self):
        return f"Demande {self.produit} - {self.quantite}"

    def clean(self):
        if self.quantite <= 0:
            raise ValidationError("La quantité doit être positive.")

    def approuver(self):
        if self.statut == "EN_ATTENTE":
            self.statut = "APPROUVE"
            self.save()
            BonCommandeInterne.objects.create(demande=self)
        else:
            raise ValidationError("Statut invalide pour approbation")


class BonCommandeInterne(models.Model):
    demande = models.OneToOneField(
        DemandeInterne, on_delete=models.PROTECT, related_name="commande_interne"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey(
        "rh.Personnel", on_delete=models.PROTECT, verbose_name="Responsable"
    )
    numero_commande = models.CharField("Numéro de commande", max_length=50, unique=True)

    class Meta:
        verbose_name = "Bon de commande interne"
        verbose_name_plural = "Bons de commande interne"

    def save(self, *args, **kwargs):
        if not self.numero_commande:
            self.numero_commande = (
                f"CMDINT-{timezone.now().strftime('%Y%m%d')}-{self.id}"
            )
        super().save(*args, **kwargs)
        self.creer_transfert()

    def creer_transfert(self):
        from pharmacies.models import Stock, Transfert
        from medical.models import Service

        pharmacie = Service.objects.get(code="PHARMACIE")
        produit = self.demande.produit

        stocks = Stock.objects.filter(
            produit=produit, service=pharmacie, quantite__gt=0
        ).order_by("date_peremption")

        quantite_restante = self.demande.quantite

        for stock in stocks:
            if quantite_restante <= 0:
                break

            quantite_transferee = min(stock.quantite, quantite_restante)

            Transfert.objects.create(
                produit=produit,
                service_origine=pharmacie,
                service_destination=self.demande.service_demandeur,
                quantite_transferee=quantite_transferee,
                responsable=self.responsable,
                numero_lot=stock.numero_lot,
                date_peremption=stock.date_peremption,
            )

            quantite_restante -= quantite_transferee


class BonLivraisonInterne(models.Model):
    transfert = models.OneToOneField(
        "pharmacies.Transfert",
        on_delete=models.PROTECT,
        related_name="livraison_interne",
    )
    date_livraison = models.DateTimeField(auto_now_add=True)
    numero_bl = models.CharField("Numéro BL interne", max_length=50, unique=True)

    class Meta:
        verbose_name = "Bon de livraison interne"
        verbose_name_plural = "Bons de livraison interne"

    def save(self, *args, **kwargs):
        if not self.numero_bl:
            self.numero_bl = f"BLINT-{self.date_livraison.strftime('%Y%m%d')}-{self.id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Livraison interne {self.numero_bl}"


# pharmacies/models/stock.py

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class StockManager(models.Manager):
    def get_available(self, produit, service):
        return self.filter(
            produit=produit,
            service=service,
            quantite__gt=0,
            date_peremption__gte=timezone.now().date(),
        ).order_by("date_peremption")

    def update_or_create_stock(
        self, produit, service, date_peremption, numero_lot, quantite
    ):
        with transaction.atomic():
            stock, created = self.select_for_update().get_or_create(
                produit=produit,
                service=service,
                date_peremption=date_peremption,
                numero_lot=numero_lot,
                defaults={"quantite": quantite},
            )

            if not created:
                stock.quantite += quantite
                stock.save()

            return stock


class Stock(models.Model):
    produit = models.ForeignKey(
        "Produit", on_delete=models.PROTECT, verbose_name="Produit"
    )
    service = models.ForeignKey(
        "medical.Service", on_delete=models.PROTECT, verbose_name="Service"
    )
    quantite = models.PositiveIntegerField(verbose_name="Quantité")
    date_peremption = models.DateField(verbose_name="Date de péremption")
    numero_lot = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Numéro de lot"
    )
    date_ajout = models.DateTimeField(auto_now_add=True, verbose_name="Date d'ajout")

    objects = StockManager()

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"

        indexes = [
            models.Index(fields=["date_peremption"]),
            models.Index(fields=["numero_lot"]),
        ]

    def __str__(self):
        return f"{self.produit} | {self.service} | Qté: {self.quantite} | Exp: {self.date_peremption}"

    def clean(self):
        if self.date_peremption < timezone.now().date():
            raise ValidationError(
                "La date de péremption ne peut pas être dans le passé"
            )


class MouvementStock(models.Model):
    TYPES_MOUVEMENT = (
        ("ENTREE", "Entrée de stock"),
        ("SORTIE", "Sortie de stock"),
        ("TRANSFERT_ENTREE", "Transfert (entrée)"),
        ("TRANSFERT_SORTIE", "Transfert (sortie)"),
        ("AJUSTEMENT", "Ajustement"),
    )

    type_mouvement = models.CharField(max_length=17, choices=TYPES_MOUVEMENT)
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    service = models.ForeignKey("medical.Service", on_delete=models.PROTECT)
    quantite = models.IntegerField()
    lot_concerne = models.CharField(max_length=50, blank=True, null=True)
    date_mouvement = models.DateTimeField(auto_now_add=True)

    # Generic foreign key pour lier à n'importe quel modèle
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    source = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        indexes = [
            models.Index(fields=["type_mouvement"]),
            models.Index(fields=["date_mouvement"]),
        ]

    @classmethod
    def log_mouvement(cls, instance, type_mouvement, **kwargs):
        """Méthode générique pour logger les mouvements"""
        return cls.objects.create(
            type_mouvement=type_mouvement,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            **kwargs,
        )


class TransfertManager(models.Manager):
    def create_transfert(self, **kwargs):
        with transaction.atomic():
            # Verrouillage des stocks concernés
            stock_origine = Stock.objects.select_for_update().get(
                produit=kwargs["produit"],
                service=kwargs["service_origine"],
                numero_lot=kwargs["numero_lot"],
                date_peremption=kwargs["date_peremption"],
            )

            if stock_origine.quantite < kwargs["quantite_transferee"]:
                raise ValidationError("Stock insuffisant pour le transfert")

            transfert = self.create(**kwargs)

            # Mise à jour stock origine
            stock_origine.quantite -= transfert.quantite_transferee
            stock_origine.save()

            # Création stock destination
            Stock.objects.create(
                produit=transfert.produit,
                service=transfert.service_destination,
                quantite=transfert.quantite_transferee,
                date_peremption=transfert.date_peremption,
                numero_lot=transfert.numero_lot,
            )

            # Log des mouvements
            MouvementStock.log_mouvement(
                instance=transfert,
                type_mouvement="TRANSFERT_SORTIE",
                produit=transfert.produit,
                service=transfert.service_origine,
                quantite=-transfert.quantite_transferee,
                lot_concerne=transfert.numero_lot,
            )

            MouvementStock.log_mouvement(
                instance=transfert,
                type_mouvement="TRANSFERT_ENTREE",
                produit=transfert.produit,
                service=transfert.service_destination,
                quantite=transfert.quantite_transferee,
                lot_concerne=transfert.numero_lot,
            )

            return transfert


class Transfert(models.Model):
    produit = models.ForeignKey(
        "Produit", on_delete=models.PROTECT, verbose_name="Produit"
    )
    service_origine = models.ForeignKey(
        "medical.Service",
        related_name="transferts_sortants",
        on_delete=models.PROTECT,
        verbose_name="Service d'origine",
    )
    service_destination = models.ForeignKey(
        "medical.Service",
        related_name="transferts_entrants",
        on_delete=models.PROTECT,
        verbose_name="Service de destination",
    )
    quantite_transferee = models.PositiveIntegerField(
        verbose_name="Quantité transférée"
    )
    responsable = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.PROTECT,
        verbose_name="Responsable du transfert",
    )
    date_transfert = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de transfert"
    )
    date_peremption = models.DateField(verbose_name="Date de péremption")
    numero_lot = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Numéro de lot"
    )
    commande_interne = models.ForeignKey(
        "BonCommandeInterne",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts",
    )
    objects = TransfertManager()

    class Meta:
        verbose_name = "Transfert"
        verbose_name_plural = "Transferts"

    def __str__(self):
        return f"Transfert {self.produit} de {self.service_origine} à {self.service_destination}"


class AjustementStock(models.Model):
    MOTIFS_AJUSTEMENT = (
        ("ERREUR", "Erreur de saisie"),
        ("DOMMAGE", "Produit endommagé"),
        ("PERDU", "Produit perdu"),
        ("INVENTAIRE", "Ajustement inventaire"),
    )

    stock = models.ForeignKey(Stock, on_delete=models.PROTECT)
    quantite_avant = models.IntegerField()
    quantite_apres = models.IntegerField()
    motif = models.CharField(max_length=15, choices=MOTIFS_AJUSTEMENT)
    commentaire = models.TextField(blank=True)
    date_ajustement = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey("rh.Personnel", on_delete=models.PROTECT)

    def save(self, *args, **kwargs):
        delta = self.quantite_apres - self.quantite_avant
        mouvement_type = "AJUSTEMENT"

        super().save(*args, **kwargs)

        MouvementStock.log_mouvement(
            instance=self,
            type_mouvement=mouvement_type,
            produit=self.stock.produit,
            service=self.stock.service,
            quantite=delta,
            lot_concerne=self.stock.numero_lot,
        )


class ConsommationProduit(models.Model):
    prestation_acte = models.ForeignKey(
        "medical.PrestationActe", on_delete=models.CASCADE, related_name="consommations"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite_defaut = models.PositiveIntegerField()
    quantite_reelle = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    montant_solde = models.DecimalField(max_digits=10, decimal_places=2)
    date_consommation = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["prestation_acte"]),
            models.Index(fields=["produit"]),
        ]

    def save(self, *args, **kwargs):
        # Calcul du montant soldé
        self.montant_solde = (
            self.quantite_reelle - self.quantite_defaut
        ) * self.prix_unitaire

        # Application sur le stock
        if self.pk is None:  # Seulement à la création
            service = self.prestation_acte.acte.service
            stocks = Stock.objects.get_available(self.produit, service)
            quantite_restante = self.quantite_reelle

            with transaction.atomic():
                for stock in stocks.select_for_update():
                    if quantite_restante <= 0:
                        break

                    prelevement = min(quantite_restante, stock.quantite)
                    stock.quantite -= prelevement
                    stock.save()

                    MouvementStock.log_mouvement(
                        instance=self,
                        type_mouvement="SORTIE",
                        produit=self.produit,
                        service=service,
                        quantite=-prelevement,
                        lot_concerne=stock.numero_lot,
                    )

                    quantite_restante -= prelevement

                if quantite_restante > 0:
                    raise ValidationError("Stock insuffisant pour la consommation")

        super().save(*args, **kwargs)


# medical/models/services.py

from django.db import models


class Service(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    est_stockeur = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name


# medical.models
from decimal import Decimal
from django.db.models import F

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from pharmacies.models import ConsommationProduit, Stock
from finance.models import (
    HonorairesMedecin,
    TarifActeConvention,
    TarifActe,
)


class Acte(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    service = models.ForeignKey(
        "Service", on_delete=models.PROTECT, related_name="actes"
    )

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
    honoraire_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Honoraire médecin total",
        null=True,
        blank=True,
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

    # def update_stock(self):
    #     """Met à jour le stock par service concerné"""

    #     for consommation in ConsommationProduit.objects.filter(
    #         prestation_acte__prestation=self
    #     ):
    #         service = consommation.prestation_acte.acte.service
    #         Stock.objects.filter(
    #             produit=consommation.produit, service=service
    #         ).update(quantite=F("quantite") - consommation.quantite_reelle)


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
        if self.tarif_conventionne < Decimal("0"):
            raise ValidationError("Le tarif ne peut pas être négatif")

        if self.honoraire_medecin < Decimal("0"):
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
