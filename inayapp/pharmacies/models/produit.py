# pharmacies/models/produit.py
from django.db import models
from django.urls import reverse
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

class CategorieProduit(models.Model):
    """Catégories hiérarchiques de produits"""

    nom = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    # description = models.TextField(blank=True)
    marge_beneficiaire_defaut = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="Marge bénéficiaire par défaut en %",
    )
    tva_applicable = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("19.00"),
        help_text="Taux TVA applicable en %",
    )

    class Meta:
        verbose_name = "Catégorie produit"
        verbose_name_plural = "Catégories produits"

    def __str__(self):
        return self.nom





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

    def stock_critique(self, seuil=10):
        """Produits avec stock critique"""
        from .stock import Stock

        return self.filter(
            stocks__quantite__lte=seuil, stocks__quantite__gt=0
        ).distinct()

    def expires_bientot(self, jours=30):
        """Produits expirant bientôt"""
        limite = timezone.now().date() + timedelta(days=jours)
        from .stock import Stock

        return self.filter(
            stocks__date_peremption__lte=limite, stocks__quantite__gt=0
        ).distinct()


class Produit(models.Model):
    """Modèle représentant un produit de pharmacie"""

    class TypeProduit(models.TextChoices):
        MEDICAMENT = "MED", "Médicament"
        CONSOMMABLE = "CONS", "Consommable"
        DISPOSITIF = "DISP", "Dispositif médical"
        REACTIF = "REAC", "Réactif"

    class ClasseMedicament(models.TextChoices):
        GENERIQUE = "GEN", "Générique"
        PRINCEPS = "PRIN", "Princeps"
        BIOSIMILAIRE = "BIO", "Biosimilaire"

    # Identification
    nom = models.CharField(max_length=255, verbose_name="Nom du produit")

    code_produit = models.CharField(
        max_length=50, unique=True, verbose_name="Code produit"
    )
    code_barres = models.CharField(max_length=50, unique=True, blank=True, null=True)

    # Classification
    type_produit = models.CharField(max_length=4, choices=TypeProduit.choices)


    # Prix et coûts
    prix_achat = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    prix_vente = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    est_actif = models.BooleanField(default=True)
    

    objects = ProduitManager()

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["nom"]
        indexes = [
            models.Index(fields=["code_produit"]),
            models.Index(fields=["type_produit"]),
            
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
    def stock_total(self):
        """Stock total tous services confondus"""
        return sum(stock.quantite for stock in self.stocks.all())

    @property
    def valeur_stock(self):
        """Valeur du stock au prix d'achat"""
        return self.stock_total * self.prix_achat

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
