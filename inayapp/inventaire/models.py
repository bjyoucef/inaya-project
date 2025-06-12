# inventaire/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import uuid


class Salle(models.Model):
    nom = models.CharField(max_length=100)
    service = models.ForeignKey(
        "medical.Service", on_delete=models.CASCADE, related_name="salles"
    )
    description = models.TextField(blank=True, null=True)
    capacite = models.IntegerField(default=1, help_text="Capacité maximale")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Salle"
        verbose_name_plural = "Salles"
        unique_together = ("nom", "service")

    def __str__(self):
        return f"{self.service.name} - {self.nom}"


class CategorieItem(models.Model):
    TYPE_CHOICES = [
        ("equipement", "Équipement"),
        ("fourniture", "Fourniture"),
        ("medicament", "Médicament"),
        ("consommable", "Consommable"),
    ]

    nom = models.CharField(max_length=100, unique=True)
    type_item = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Catégorie d'item"
        verbose_name_plural = "Catégories d'items"

    def __str__(self):
        return f"{self.nom} ({self.get_type_item_display()})"


class Marque(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Marque"
        verbose_name_plural = "Marques"

    def __str__(self):
        return self.nom


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.TextField(blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    contact_personne = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

    def __str__(self):
        return self.nom


class Item(models.Model):
    ETAT_CHOICES = [
        ("neuf", "Neuf"),
        ("bon", "Bon état"),
        ("moyen", "État moyen"),
        ("mauvais", "Mauvais état"),
        ("hs", "Hors service"),
        ("reparation", "En réparation"),
        ("casse", "Cassé"),
        ("vole", "Volé"),
    ]

    nom = models.CharField(max_length=200)
    code_barre = models.CharField(max_length=50, unique=True, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True, null=True)

    categorie = models.ForeignKey(CategorieItem, on_delete=models.PROTECT)
    marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True)
    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.SET_NULL, null=True, blank=True
    )

    description = models.TextField(blank=True, null=True)
    specifications = models.JSONField(default=dict, blank=True)

    prix_achat = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    date_achat = models.DateField(null=True, blank=True)
    date_garantie = models.DateField(null=True, blank=True)

    etat = models.CharField(max_length=20, choices=ETAT_CHOICES, default="neuf")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="items_created"
    )

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Items"

    def save(self, *args, **kwargs):
        if not self.code_barre:
            self.code_barre = self.generer_code_barre()
        super().save(*args, **kwargs)

    def generer_code_barre(self):
        return f"CLI{timezone.now().year}{str(uuid.uuid4())[:8].upper()}"

    @property
    def est_sous_garantie(self):
        if self.date_garantie:
            return timezone.now().date() <= self.date_garantie
        return False

    def __str__(self):
        return f"{self.nom} ({self.code_barre})"


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stocks")
    salle = models.ForeignKey(Salle, on_delete=models.CASCADE, related_name="stocks")

    quantite = models.IntegerField(default=0)
    quantite_min = models.IntegerField(default=0, help_text="Seuil d'alerte")
    quantite_max = models.IntegerField(default=100, help_text="Stock maximum")

    emplacement = models.CharField(
        max_length=100, blank=True, null=True, help_text="Ex: Armoire A, Étagère 2"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        unique_together = ("item", "salle")

    @property
    def est_en_rupture(self):
        return self.quantite <= 0

    @property
    def est_en_alerte(self):
        return self.quantite <= self.quantite_min

    def __str__(self):
        return f"{self.item.nom} - {self.salle} ({self.quantite})"


class MouvementStock(models.Model):
    TYPE_MOUVEMENT = [
        ("entree", "Entrée"),
        ("sortie", "Sortie"),
        ("transfert", "Transfert"),
        ("inventaire", "Inventaire"),
        ("perte", "Perte"),
        ("vol", "Vol"),
        ("casse", "Casse"),
        ("reparation", "Réparation"),
        ("renovation", "Rénovation"),
        ("retour", "Retour"),
    ]

    STATUT_CHOICES = [
        ("en_attente", "En attente"),
        ("valide", "Validé"),
        ("annule", "Annulé"),
        ("en_cours", "En cours"),
        ("termine", "Terminé"),
    ]

    stock = models.ForeignKey(
        Stock, on_delete=models.CASCADE, related_name="mouvements"
    )
    type_mouvement = models.CharField(max_length=20, choices=TYPE_MOUVEMENT)
    quantite = models.IntegerField()

    # Pour les transferts
    salle_destination = models.ForeignKey(
        Salle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mouvements_entrants",
    )

    motif = models.TextField(blank=True, null=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="en_attente"
    )

    cout_reparation = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    date_mouvement = models.DateTimeField(default=timezone.now)
    date_validation = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="mouvements_created"
    )
    validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="mouvements_validated"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-date_mouvement"]

    def valider(self, user):
        if self.statut == "en_attente":
            self.statut = "valide"
            self.validated_by = user
            self.date_validation = timezone.now()
            self.save()

            # Appliquer le mouvement au stock
            self.appliquer_mouvement()

    def appliquer_mouvement(self):
        if self.type_mouvement == "entree":
            self.stock.quantite += self.quantite
        elif self.type_mouvement in ["sortie", "perte", "vol", "casse"]:
            self.stock.quantite -= self.quantite
        elif self.type_mouvement == "transfert" and self.salle_destination:
            # Sortie du stock source
            self.stock.quantite -= self.quantite

            # Entrée dans le stock destination
            stock_dest, created = Stock.objects.get_or_create(
                item=self.stock.item,
                salle=self.salle_destination,
                defaults={"quantite": 0},
            )
            stock_dest.quantite += self.quantite
            stock_dest.save()

        # Assurer que la quantité ne devient pas négative
        if self.stock.quantite < 0:
            self.stock.quantite = 0

        self.stock.save()

    def __str__(self):
        return f"{self.get_type_mouvement_display()} - {self.stock.item.nom} ({self.quantite})"


class DemandeTransfert(models.Model):
    STATUT_CHOICES = [
        ("en_attente", "En attente"),
        ("approuve", "Approuvé"),
        ("refuse", "Refusé"),
        ("execute", "Exécuté"),
        ("annule", "Annulé"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    salle_source = models.ForeignKey(
        Salle, on_delete=models.CASCADE, related_name="transferts_sortants"
    )
    salle_destination = models.ForeignKey(
        Salle, on_delete=models.CASCADE, related_name="transferts_entrants"
    )

    quantite = models.IntegerField()
    motif = models.TextField()
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="en_attente"
    )

    demande_par = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="demandes_transfert"
    )
    approuve_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_approuves",
    )
    execute_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_executes",
    )

    date_demande = models.DateTimeField(auto_now_add=True)
    date_approbation = models.DateTimeField(null=True, blank=True)
    date_execution = models.DateTimeField(null=True, blank=True)

    observations = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Demande de transfert"
        verbose_name_plural = "Demandes de transfert"
        ordering = ["-date_demande"]

    def approuver(self, user):
        self.statut = "approuve"
        self.approuve_par = user
        self.date_approbation = timezone.now()
        self.save()

    def executer(self, user):
        if self.statut == "approuve":
            # Créer le mouvement de transfert
            stock_source = Stock.objects.get(item=self.item, salle=self.salle_source)

            mouvement = MouvementStock.objects.create(
                stock=stock_source,
                type_mouvement="transfert",
                quantite=self.quantite,
                salle_destination=self.salle_destination,
                motif=f"Transfert demandé: {self.motif}",
                created_by=user,
                statut="valide",
            )

            mouvement.appliquer_mouvement()

            self.statut = "execute"
            self.execute_par = user
            self.date_execution = timezone.now()
            self.save()

    def __str__(self):
        return (
            f"Transfert {self.item.nom}: {self.salle_source} → {self.salle_destination}"
        )


class Inventaire(models.Model):
    STATUT_CHOICES = [
        ("planifie", "Planifié"),
        ("en_cours", "En cours"),
        ("termine", "Terminé"),
        ("valide", "Validé"),
    ]

    nom = models.CharField(max_length=200)
    salle = models.ForeignKey(
        Salle, on_delete=models.CASCADE, related_name="inventaires"
    )

    date_planifiee = models.DateField()
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="planifie")

    responsable = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="inventaires_responsable"
    )
    participants = models.ManyToManyField(
        User, blank=True, related_name="inventaires_participant"
    )

    observations = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        ordering = ["-date_planifiee"]

    def demarrer(self):
        self.statut = "en_cours"
        self.date_debut = timezone.now()
        self.save()

        # Créer les lignes d'inventaire pour tous les stocks de la salle
        for stock in self.salle.stocks.all():
            LigneInventaire.objects.get_or_create(
                inventaire=self,
                stock=stock,
                defaults={"quantite_theorique": stock.quantite, "quantite_comptee": 0},
            )

    def terminer(self):
        self.statut = "termine"
        self.date_fin = timezone.now()
        self.save()

    def valider(self):
        if self.statut == "termine":
            # Appliquer les écarts
            for ligne in self.lignes_inventaire.all():
                if ligne.ecart != 0:
                    mouvement = MouvementStock.objects.create(
                        stock=ligne.stock,
                        type_mouvement="inventaire",
                        quantite=ligne.ecart,
                        motif=f"Inventaire {self.nom} - Écart constaté",
                        created_by=self.responsable,
                        statut="valide",
                    )

                    # Ajuster le stock
                    ligne.stock.quantite = ligne.quantite_comptee
                    ligne.stock.save()

            self.statut = "valide"
            self.save()

    def __str__(self):
        return f"{self.nom} - {self.salle}"


class LigneInventaire(models.Model):
    inventaire = models.ForeignKey(
        Inventaire, on_delete=models.CASCADE, related_name="lignes_inventaire"
    )
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)

    quantite_theorique = models.IntegerField(default=0)
    quantite_comptee = models.IntegerField(default=0)

    observations = models.TextField(blank=True, null=True)
    comptee_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    date_comptage = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"
        unique_together = ("inventaire", "stock")

    @property
    def ecart(self):
        return self.quantite_comptee - self.quantite_theorique

    @property
    def statut_ecart(self):
        ecart = self.ecart
        if ecart > 0:
            return "excedent"
        elif ecart < 0:
            return "manquant"
        return "conforme"

    def compter(self, quantite, user):
        self.quantite_comptee = quantite
        self.comptee_par = user
        self.date_comptage = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.inventaire.nom} - {self.stock.item.nom}"


class MaintenanceEquipement(models.Model):
    TYPE_MAINTENANCE = [
        ("preventive", "Préventive"),
        ("corrective", "Corrective"),
        ("curative", "Curative"),
    ]

    STATUT_CHOICES = [
        ("planifiee", "Planifiée"),
        ("en_cours", "En cours"),
        ("terminee", "Terminée"),
        ("reportee", "Reportée"),
        ("annulee", "Annulée"),
    ]

    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="maintenances"
    )
    type_maintenance = models.CharField(max_length=20, choices=TYPE_MAINTENANCE)

    titre = models.CharField(max_length=200)
    description = models.TextField()

    date_planifiee = models.DateField()
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="planifiee"
    )

    technicien = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenances_technicien",
    )
    cout = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    rapport = models.TextField(blank=True, null=True)
    pieces_changees = models.TextField(blank=True, null=True)

    prochaine_maintenance = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="maintenances_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Maintenance d'équipement"
        verbose_name_plural = "Maintenances d'équipements"
        ordering = ["-date_planifiee"]

    def demarrer(self, user):
        self.statut = "en_cours"
        self.date_debut = timezone.now()
        self.technicien = user

        # Mettre l'équipement en réparation
        self.item.etat = "reparation"
        self.item.save()
        self.save()

    def terminer(self, rapport, nouveau_etat="bon"):
        self.statut = "terminee"
        self.date_fin = timezone.now()
        self.rapport = rapport

        # Remettre l'équipement en service
        self.item.etat = nouveau_etat
        self.item.save()
        self.save()

    def __str__(self):
        return f"{self.get_type_maintenance_display()} - {self.item.nom}"
