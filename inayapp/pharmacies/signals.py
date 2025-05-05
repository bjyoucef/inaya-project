from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Transfert, Stock, Consommation


@receiver(post_save, sender=Transfert)
def gerer_transfert_stock(sender, instance, created, **kwargs):
    if created:
        # Déduire du stock du service d'origine
        stock_source = Stock.objects.filter(
            produit=instance.produit,
            service=instance.service_origine,
            date_peremption=instance.date_peremption,
            numero_lot=instance.numero_lot,
        ).first()

        if stock_source and stock_source.quantite >= instance.quantite_transferee:
            stock_source.quantite -= instance.quantite_transferee
            stock_source.save()

            # Créer ou mettre à jour le stock du service de destination
            stock_dest, created = Stock.objects.get_or_create(
                produit=instance.produit,
                service=instance.service_destination,
                date_peremption=instance.date_peremption,
                numero_lot=instance.numero_lot,
                defaults={"quantite": instance.quantite_transferee},
            )
            if not created:
                stock_dest.quantite += instance.quantite_transferee
                stock_dest.save()


@receiver(post_save, sender=Consommation)
def mise_a_jour_stock_apres_consommation(sender, instance, created, **kwargs):
    if created:
        restant = instance.quantite_consomme
        # Récupérer les stocks non périmés, triés par date de péremption
        stocks = Stock.objects.filter(
            produit=instance.produit,
            service=instance.service,
            date_peremption__gte=timezone.now().date(),
        ).order_by("date_peremption")

        for stock in stocks:
            if restant <= 0:
                break
            a_deduire = min(restant, stock.quantite)
            stock.quantite -= a_deduire
            stock.save()
            restant -= a_deduire

        if restant > 0:
            raise ValidationError(
                f"Stock insuffisant pour {instance.produit}. Manquant: {restant}"
            )

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=BonLivraison)
def set_numero_bl(sender, instance, created, **kwargs):
    if created and not instance.numero_bl:
        instance.numero_bl = f"BL-{timezone.now().strftime('%Y%m%d')}-{instance.id}"
        instance.save(update_fields=["numero_bl"])
