# pharmacies/models/commande.py

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from ..models import MouvementStock, Stock


class Achat(models.Model):
    livraison = models.ForeignKey(
        'BonLivraison', 
        on_delete=models.SET_NULL,
        null=True,
        related_name='achats'
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
    date_peremption = models.DateTimeField(verbose_name="Date de péremption"
    )

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
    date_commande = models.DateTimeField( auto_now_add=True)
    date_livraison_prevue = models.DateTimeField(
    )
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
    date_peremption = models.DateTimeField(
    )
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
        if not hasattr(self, 'commande') or self.commande.statut not in ["VALIDE", "LIVRE"]:
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
