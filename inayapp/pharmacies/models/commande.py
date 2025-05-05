# pharmacies/models.py

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Achat(models.Model):
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
    date_peremption = models.DateField(verbose_name="Date de péremption")

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
        if self.date_peremption < timezone.now().date():
            raise ValidationError(
                "La date de péremption ne peut pas être dans le passé"
            )

        is_new = not self.pk
        super().save(*args, **kwargs)

        if is_new:
            stock = Stock.objects.create(
                produit=self.produit,
                service=self.service_destination,
                quantite=self.quantite_achetee,
                date_peremption=self.date_peremption,
                numero_lot=self.numero_lot,
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
    numero_commande = models.CharField("Numéro de commande", max_length=50, unique=True)
    date_commande = models.DateField(auto_now_add=True)
    date_livraison_prevue = models.DateField()
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="BROUILLON"
    )
    commentaire = models.TextField(blank=True)
    service_destination = models.ForeignKey("medical.Service", on_delete=models.PROTECT)

    class Meta:
        ordering = ["-date_commande"]
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"

    def __str__(self):
        return f"CMD-{self.numero_commande}"

    @property
    def montant_total(self):
        return sum(ligne.montant for ligne in self.lignes.all())


class LigneCommande(models.Model):
    commande = models.ForeignKey(
        BonCommande, on_delete=models.CASCADE, related_name="lignes"
    )
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    date_peremption = models.DateField()
    numero_lot = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    @property
    def montant(self):
        return self.quantite * self.prix_unitaire


class BonLivraison(models.Model):
    commande = models.ForeignKey(
        BonCommande, on_delete=models.PROTECT, related_name="livraisons"
    )
    numero_bl = models.CharField(max_length=50, unique=True)
    date_livraison = models.DateField(auto_now_add=True)
    fichier_bl = models.FileField(upload_to="bl/", blank=True, null=True)
    est_complet = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.numero_bl:
            self.numero_bl = f"BL-{self.date_livraison.strftime('%Y%m%d')}-{self.id}"
        super().save(*args, **kwargs)
        self.mettre_a_jour_stock()

    def mettre_a_jour_stock(self):
        for ligne in self.commande.lignes.all():
            Stock.objects.create(
                produit=ligne.produit,
                service=self.commande.service_destination,
                quantite=ligne.quantite,
                date_peremption=ligne.date_peremption,
                numero_lot=ligne.numero_lot,
            )
