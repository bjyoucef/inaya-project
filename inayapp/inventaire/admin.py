# inventaire/admin.py
from django.contrib import admin
from .models import *


@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ("nom", "service", "capacite", "created_at")
    list_filter = ("service", "created_at")
    search_fields = ("nom", "service__name")


@admin.register(CategorieItem)
class CategorieItemAdmin(admin.ModelAdmin):
    list_display = ("nom", "type_item")
    list_filter = ("type_item",)
    search_fields = ("nom",)


@admin.register(Marque)
class MarqueAdmin(admin.ModelAdmin):
    list_display = ("nom",)
    search_fields = ("nom",)


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ("nom", "telephone", "email", "contact_personne")
    search_fields = ("nom", "contact_personne", "email")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        "nom",
        "code_barre",
        "categorie",
        "marque",
        "etat",
        "est_sous_garantie",
    )
    list_filter = ("categorie", "marque", "etat", "created_at")
    search_fields = ("nom", "code_barre", "numero_serie")
    readonly_fields = ("code_barre", "created_at", "updated_at", "est_sous_garantie")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "salle",
        "quantite",
        "quantite_min",
        "est_en_alerte",
        "est_en_rupture",
    )
    list_filter = ("salle__service", "salle", "updated_at")
    search_fields = ("item__nom", "salle__nom")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("item", "salle", "salle__service")
        )


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "type_mouvement",
        "quantite",
        "statut",
        "date_mouvement",
        "created_by",
    )
    list_filter = ("type_mouvement", "statut", "date_mouvement")
    search_fields = ("stock__item__nom", "motif")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DemandeTransfert)
class DemandeTransfertAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "salle_source",
        "salle_destination",
        "quantite",
        "statut",
        "demande_par",
        "date_demande",
    )
    list_filter = (
        "statut",
        "date_demande",
        "salle_source__service",
        "salle_destination__service",
    )
    search_fields = ("item__nom", "motif")


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ("nom", "salle", "date_planifiee", "statut", "responsable")
    list_filter = ("statut", "date_planifiee", "salle__service")
    search_fields = ("nom", "salle__nom")


@admin.register(LigneInventaire)
class LigneInventaireAdmin(admin.ModelAdmin):
    list_display = (
        "inventaire",
        "stock",
        "quantite_theorique",
        "quantite_comptee",
        "ecart",
        "statut_ecart",
    )
    list_filter = ("inventaire__statut", "date_comptage")
    search_fields = ("inventaire__nom", "stock__item__nom")


@admin.register(MaintenanceEquipement)
class MaintenanceEquipementAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "type_maintenance",
        "date_planifiee",
        "statut",
        "technicien",
        "cout",
    )
    list_filter = ("type_maintenance", "statut", "date_planifiee")
    search_fields = ("item__nom", "titre", "description")
