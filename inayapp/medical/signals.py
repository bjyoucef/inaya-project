# medical/signals.py

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from medical.models.services import Service


def _make_codename(name):
    return f"view_service_{slugify(name).replace('-', '_')}"


@receiver(pre_save, sender=Service)
def rename_service_permission(sender, instance, **kwargs):
    if not instance.pk:
        return  # Création gérée par post_save

    old = Service.objects.get(pk=instance.pk)
    if old.name != instance.name:
        ct = ContentType.objects.get_for_model(Service)
        old_codename = _make_codename(old.name)

        try:
            perm = Permission.objects.get(codename=old_codename, content_type=ct)
        except Permission.DoesNotExist:
            return

        new_codename = _make_codename(instance.name)
        new_name = f"Peut voir le service {instance.name}"

        perm.codename = new_codename
        perm.name = new_name
        perm.save()


@receiver(post_save, sender=Service)
def create_service_permission(sender, instance, created, **kwargs):
    if created:
        content_type = ContentType.objects.get_for_model(Service)
        codename = _make_codename(instance.name)
        name = f"Peut voir le service {instance.name}"
        Permission.objects.get_or_create(
            codename=codename, name=name, content_type=content_type
        )


@receiver(post_delete, sender=Service)
def delete_service_permission(sender, instance, **kwargs):
    ct = ContentType.objects.get_for_model(Service)
    codename = _make_codename(instance.name)
    Permission.objects.filter(codename=codename, content_type=ct).delete()
