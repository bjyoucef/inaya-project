# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Theme
from django.contrib.auth.models import User


@receiver(post_save, sender=User)
def create_theme_profile(sender, instance, created, **kwargs):
    if created:
        Theme.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_theme_profile(sender, instance, **kwargs):
    instance.theme.save()
