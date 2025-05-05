# pharmacies/models.py

from django.db import models

class Produit(models.Model):
    TYPES_PRODUIT = (
        ("MED", "Médicament"),
        ("CONS", "Consommable"),
    )

    nom = models.CharField(max_length=255, verbose_name="Nom")
    code_produit = models.CharField(
        max_length=50, unique=True, verbose_name="Code produit"
    )
    code_barres = models.CharField(
        max_length=50, unique=True, blank=True, null=True, verbose_name="Code-barres"
    )
    type_produit = models.CharField(
        max_length=4, choices=TYPES_PRODUIT, verbose_name="Type de produit"
    )
    prix_achat = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Prix d'achat"
    )
    prix_vente = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Prix de vente"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    est_actif = models.BooleanField(default=True, verbose_name="Actif")

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
