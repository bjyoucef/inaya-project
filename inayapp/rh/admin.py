from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils.crypto import get_random_string
from django.utils.encoding import force_str
from django.utils.text import slugify
from django.utils.translation import gettext as _
from import_export.admin import ImportExportModelAdmin

from .models import AnvizConfiguration, HonorairesActe, Personnel, Poste, JourFerie
from .resources import PersonnelResource, PosteResource


from import_export.admin import ImportExportModelAdmin


class PatchedImportExportAdmin(ImportExportModelAdmin):
    """
    Surcharge _create_log_entry pour ne rien logger
    (évite toute incompatibilité avec LogEntryManager.log_actions).
    """

    def _create_log_entry(self, *args, **kwargs):
        # On ne fait rien. Si besoin, vous pouvez créer manuellement un LogEntry ici.
        return


@admin.register(Personnel)
class PersonnelAdmin(PatchedImportExportAdmin):
    resource_class = PersonnelResource
    list_display = ("nom_prenom", "service", "poste", "salaire", "get_username")
    search_fields = ("nom_prenom", "service__name", "poste__label")

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


@admin.register(AnvizConfiguration)
class AnvizDeviceConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip_address', 'username', 'is_active', 'last_modified')


admin.site.register(HonorairesActe)
admin.site.register(JourFerie)


@admin.register(Poste)
class PosteAdmin(PatchedImportExportAdmin):
    resource_class = PosteResource
    list_display = ("label",)
    search_fields = ("label",)
