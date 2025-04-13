from django.contrib import admin
from .models import Personnel ,Services ,HonorairesActe
from django.contrib import messages


admin.site.register(Services)
admin.site.register(HonorairesActe)


class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("nom_prenom", "role", "get_username")
    
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

admin.site.register(Personnel, PersonnelAdmin)
