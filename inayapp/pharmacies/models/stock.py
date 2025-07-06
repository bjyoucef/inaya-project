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
    quantite = models.IntegerField(verbose_name="Quantité")
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

    type_mouvement = models.CharField(max_length=20, choices=TYPES_MOUVEMENT)
    produit = models.ForeignKey("Produit", on_delete=models.PROTECT)
    service = models.ForeignKey("medical.Service", on_delete=models.PROTECT)
    quantite = models.IntegerField()
    lot_concerne = models.CharField(max_length=50, blank=True, null=True)
    date_mouvement = models.DateTimeField(auto_now_add=True)

    # Generic foreign key pour lier à n'importe quel modèle
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    instance = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        indexes = [
            models.Index(fields=["type_mouvement"]),
            models.Index(fields=["date_mouvement"]),
            models.Index(fields=["produit"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    @classmethod
    def log_mouvement(
        cls,
        instance,
        type_mouvement,
        produit,
        service,
        quantite,
        lot_concerne=None,
        **kwargs
    ):
        """
        Log a stock movement with proper GenericForeignKey handling
        """
        return cls.objects.create(
            type_mouvement=type_mouvement,
            produit=produit,
            service=service,
            quantite=quantite,
            lot_concerne=lot_concerne,
            instance=instance,  # This will automatically set content_type and object_id
            **kwargs,
        )


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
    montant_solde = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    date_consommation = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["prestation_acte"]),
            models.Index(fields=["produit"]),
        ]

    def save(self, *args, **kwargs):
        # Calculer le montant soldé
        self.montant_solde = (
            self.quantite_reelle - self.quantite_defaut
        ) * self.prix_unitaire

        # Sauvegarder d'abord pour avoir un ID
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Appliquer sur le stock seulement lors de la création
        if is_new:
            self._update_stock()

    def _update_stock(self):
        """Mise à jour du stock après consommation"""
        if self.quantite_reelle <= 0:
            return

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

                # Enregistrer le mouvement de stock
                MouvementStock.log_mouvement(
                    instance=self,
                    type_mouvement="SORTIE",
                    produit=self.produit,
                    service=service,
                    quantite=prelevement,  # Quantité positive pour le log
                    lot_concerne=stock.numero_lot,
                )

                quantite_restante -= prelevement

            # Si on n'a pas pu prélever assez de stock
            if quantite_restante > 0:
                # On peut soit lever une exception, soit loguer un warning
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Stock insuffisant pour le produit {self.produit.nom} "
                    f"dans le service {service.name}. Manque: {quantite_restante}"
                )
