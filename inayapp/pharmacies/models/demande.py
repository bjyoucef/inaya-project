# pharmacies/models/demande.py
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
