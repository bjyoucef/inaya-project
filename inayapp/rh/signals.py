import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from medical.models import Service

from .models import Personnel

User = get_user_model()

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
