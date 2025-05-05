# pharmacies/models.py

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
        constraints = [
            models.UniqueConstraint(
                fields=["produit", "service", "date_peremption", "numero_lot"],
                name="unique_stock_entry",
            )
        ]
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
