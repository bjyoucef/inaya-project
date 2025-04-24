from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from medical.models import Service
from django.utils.text import slugify
from django.contrib.auth.models import User
from .models import Personnel
from django.contrib.auth import get_user_model
import secrets
from django.core.exceptions import ValidationError
import string

User = get_user_model()

@receiver(post_save, sender=Service)
def create_service_permission(sender, instance, created, **kwargs):
    if created:
        content_type = ContentType.objects.get_for_model(Service)
        codename = f'view_service_{slugify(instance.service_name).replace("-", "_")}'
        name = f'Peut voir le service {instance.service_name}'
        Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type
        )






def generate_unique_username(base_username):
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username

@receiver(post_save, sender=Personnel)
def create_user_for_personnel(sender, instance, created, **kwargs):
    if created and not instance.user:
        base_username = instance.nom_prenom.replace(" ", "").lower()
        
        # Validation : Vérifier si le nom est valide
        if not base_username.isalnum():  # Vérifier que le nom d'utilisateur contient seulement des lettres et chiffres
            raise ValidationError("Le nom d'utilisateur ne peut contenir que des lettres et des chiffres.")
        
        # Générer un nom d'utilisateur unique
        username = generate_unique_username(base_username)
        
        # Générer un mot de passe temporaire
        temp_password = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Création de l'utilisateur
        try:
            user = User.objects.create_user(
                username=username,
                password=temp_password
            )

            instance.user = user
            instance.save()

            # Stocker le mot de passe temporaire pour l'affichage dans l'admin
            instance._temp_password = temp_password
        
        except Exception as e:
            raise ValidationError(f"Une erreur est survenue lors de la création de l'utilisateur: {str(e)}")
