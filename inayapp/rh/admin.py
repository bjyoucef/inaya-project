from django.contrib import admin, messages

from .models import AnvizConfiguration, HonorairesActe, Personnel, Poste


class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("nom_prenom", "get_username")
    search_fields = ("nom_prenom", "poste__label")
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if not change and hasattr(obj, "_temp_password"):
            messages.success(
                request,
                f"Utilisateur créé: **{obj.user.username}**, mot de passe temporaire: **{obj._temp_password}**"
            )

    def get_username(self, obj):
        return obj.user.username if obj.user else "-"
    get_username.short_description = "Nom d'utilisateur"


@admin.register(AnvizConfiguration)
class AnvizDeviceConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip_address', 'username', 'is_active', 'last_modified')

admin.site.register(Personnel, PersonnelAdmin)
admin.site.register(HonorairesActe)
admin.site.register(Poste)
