from django.contrib import admin, messages
from django.utils.text import slugify
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from .models import AnvizConfiguration, HonorairesActe, Personnel, Poste


class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("nom_prenom", "get_username")
    search_fields = ("nom_prenom", "poste__label")

    def save_model(self, request, obj, form, change):
        # Lors de la création d'un nouveau Personnel, générer automatiquement l'utilisateur
        if not change and not obj.user:
            # Extraire prénom et nom
            parts = obj.nom_prenom.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            # Générer un username à partir de nom_prenom
            base_username = slugify(obj.nom_prenom)
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            # Générer un mot de passe temporaire
            temp_password = get_random_string(length=12)
            # Créer l'utilisateur
            user = User.objects.create_user(
                username=username,
                password=temp_password,
                first_name=first_name,
                last_name=last_name,
            )
            # Associer à l'objet Personnel
            obj.user = user
            # Stocker le mot de passe temporaire pour l'afficher dans le message
            obj._temp_password = temp_password

        # Sauvegarde de l'objet Personnel (lié à l'user si créé)
        super().save_model(request, obj, form, change)

        # Afficher un message de succès si nouvel utilisateur créé
        if not change and hasattr(obj, "_temp_password"):
            messages.success(
                request,
                f"Utilisateur créé: **{obj.user.username}**, mot de passe temporaire: **{obj._temp_password}**",
            )

    def get_username(self, obj):
        return obj.user.username if obj.user else "-"

    get_username.short_description = "Nom d'utilisateur"


admin.site.register(Personnel, PersonnelAdmin)


@admin.register(AnvizConfiguration)
class AnvizDeviceConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip_address', 'username', 'is_active', 'last_modified')


admin.site.register(HonorairesActe)
admin.site.register(Poste)
