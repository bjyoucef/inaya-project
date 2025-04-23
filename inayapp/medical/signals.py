from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify

from .models import Service


def _make_codename(name):
    # slugify + underscore, identique à votre logique create
    return f"view_service_{slugify(name).replace('-', '_')}"


@receiver(pre_save, sender=Service)
def rename_service_permission(sender, instance, **kwargs):
    """
    Si le name du Service change, on renomme la permission associée.
    """
    if not instance.pk:
        # pas encore en base → c'est une création => on laisse post_save gérer
        return

    # charger l'ancien
    old = Service.objects.get(pk=instance.pk)
    if old.name != instance.name:
        ct = ContentType.objects.get_for_model(Service)

        old_codename = _make_codename(old.name)
        try:
            perm = Permission.objects.get(codename=old_codename, content_type=ct)
        except Permission.DoesNotExist:
            return  # si pas de perm existante, on ne fait rien

        # nouveau codename et nom
        new_codename = _make_codename(instance.name)
        new_name = f"Peut voir le service {instance.name}"

        # mise à jour
        perm.codename = new_codename
        perm.name = new_name
        perm.save()


@receiver(post_save, sender=Service)
def create_service_permission(sender, instance, created, **kwargs):
    """
    Création de la permission si nouveau service.
    """
    if created:
        ct = ContentType.objects.get_for_model(Service)
        codename = _make_codename(instance.name)
        name = f"Peut voir le service {instance.name}"
        Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={"name": name},
        )


@receiver(post_delete, sender=Service)
def delete_service_permission(sender, instance, **kwargs):
    """
    Suppression de la permission associée au service supprimé.
    """
    ct = ContentType.objects.get_for_model(Service)
    codename = _make_codename(instance.name)
    Permission.objects.filter(codename=codename, content_type=ct).delete()
