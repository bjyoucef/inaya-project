# pharmacies/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import  Stock, Consommation


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



