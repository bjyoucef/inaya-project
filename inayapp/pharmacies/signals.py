# pharmacies/signals.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Consommation, Stock
from .models.approvisionnement_interne import DemandeInterne
from .models.stock import MouvementStock


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


@receiver(post_save, sender=DemandeInterne)
def notifier_changement_statut_demande(sender, instance, created, **kwargs):
    """
    Envoie des notifications lors des changements de statut d'une demande
    """

    if created:
        # Nouvelle demande créée - notifier la pharmacie
        notifier_nouvelle_demande(instance)
    else:
        # Changement de statut - notifier selon le statut
        if instance.statut == "VALIDEE":
            notifier_demande_validee(instance)
        elif instance.statut == "REJETEE":
            notifier_demande_rejetee(instance)
        elif instance.statut == "PREPAREE":
            notifier_demande_preparee(instance)
        elif instance.statut == "LIVREE":
            notifier_demande_livree(instance)


def notifier_nouvelle_demande(demande):
    """Notifie la pharmacie qu'une nouvelle demande a été créée"""

    # Récupérer les utilisateurs de la pharmacie ayant les permissions
    from django.contrib.auth import get_user_model

    User = get_user_model()

    pharmaciens = User.objects.filter(
        service=demande.pharmacie,
        user_permissions__codename="can_validate_demande_interne",
    ).distinct()

    if not pharmaciens.exists():
        return

    subject = f"Nouvelle demande d'approvisionnement - {demande.reference}"

    context = {
        "demande": demande,
        "url_detail": f"{settings.SITE_URL}/pharmacies/demandes-internes/{demande.id}/",
    }

    message = render_to_string("pharmacies/emails/nouvelle_demande.html", context)

    recipients = [user.email for user in pharmaciens if user.email]

    if recipients:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=message,
            fail_silently=True,
        )


def notifier_demande_validee(demande):
    """Notifie le service demandeur que sa demande a été validée"""

    if not demande.creee_par.email:
        return

    subject = f"Demande validée - {demande.reference}"

    context = {
        "demande": demande,
        "url_detail": f"{settings.SITE_URL}/pharmacies/demandes-internes/{demande.id}/",
    }

    message = render_to_string("pharmacies/emails/demande_validee.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[demande.creee_par.email],
        html_message=message,
        fail_silently=True,
    )


def notifier_demande_rejetee(demande):
    """Notifie le service demandeur que sa demande a été rejetée"""

    if not demande.creee_par.email:
        return

    subject = f"Demande rejetée - {demande.reference}"

    context = {
        "demande": demande,
        "url_detail": f"{settings.SITE_URL}/pharmacies/demandes-internes/{demande.id}/",
    }

    message = render_to_string("pharmacies/emails/demande_rejetee.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[demande.creee_par.email],
        html_message=message,
        fail_silently=True,
    )


def notifier_demande_preparee(demande):
    """Notifie le service demandeur que sa demande est prête"""

    if not demande.creee_par.email:
        return

    subject = f"Demande prête à récupérer - {demande.reference}"

    context = {
        "demande": demande,
        "url_detail": f"{settings.SITE_URL}/pharmacies/demandes-internes/{demande.id}/",
    }

    message = render_to_string("pharmacies/emails/demande_preparee.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[demande.creee_par.email],
        html_message=message,
        fail_silently=True,
    )


def notifier_demande_livree(demande):
    """Notifie le service demandeur que sa demande a été livrée"""

    if not demande.creee_par.email:
        return

    subject = f"Demande livrée - {demande.reference}"

    context = {
        "demande": demande,
        "url_detail": f"{settings.SITE_URL}/pharmacies/demandes-internes/{demande.id}/",
    }

    message = render_to_string("pharmacies/emails/demande_livree.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[demande.creee_par.email],
        html_message=message,
        fail_silently=True,
    )


@receiver(post_save, sender=MouvementStock)
def verifier_stock_critique(sender, instance, created, **kwargs):
    """
    Vérifie si un produit atteint un niveau de stock critique après un mouvement
    """

    if not created or instance.type_mouvement != "SORTIE":
        return

    from .models.stock import Stock

    try:
        stock_actuel = Stock.objects.get_stock_disponible(
            produit=instance.produit, service=instance.service
        )

        # Vérifier si le stock est critique (< 10% du stock maximum ou < 5 unités)
        seuil_critique = (
            max(5, instance.produit.stock_max * 0.1)
            if hasattr(instance.produit, "stock_max")
            else 5
        )

        if stock_actuel <= seuil_critique:
            notifier_stock_critique(instance.produit, instance.service, stock_actuel)

    except Exception as e:
        # Log l'erreur mais ne pas faire échouer la transaction
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la vérification du stock critique: {e}")


def notifier_stock_critique(produit, service, stock_actuel):
    """Notifie les responsables qu'un produit a atteint un niveau critique"""

    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Récupérer les gestionnaires de stock
    gestionnaires = User.objects.filter(
        service=service, groups__name__in=["Pharmaciens", "Gestionnaires Stock"]
    ).distinct()

    if not gestionnaires.exists():
        return

    subject = f"Stock critique - {produit.nom}"

    context = {
        "produit": produit,
        "service": service,
        "stock_actuel": stock_actuel,
        "date": timezone.now(),
    }

    message = render_to_string("pharmacies/emails/stock_critique.html", context)

    recipients = [user.email for user in gestionnaires if user.email]

    if recipients:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=message,
            fail_silently=True,
        )


# Connecter les signaux lors de l'initialisation de l'application
def ready():
    """Appelé lors du démarrage de l'application Django"""
    # Les signaux sont automatiquement connectés par les décorateurs @receiver
    pass
