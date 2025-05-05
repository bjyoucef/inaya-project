# pharmacy/admin.py
from django.contrib import admin
from .models import Produit, Stock, Transfert


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = (
        "code_produit",
        "nom",
        "type_produit",
        "prix_achat",
        "prix_vente",
        "est_actif",
    )
    list_filter = ("type_produit", "est_actif")
    search_fields = ("code_produit", "nom", "code_barres")
    ordering = ("nom",)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "produit",
        "service",
        "quantite",
        "date_peremption",
        "numero_lot",
        "date_ajout",
    )
    list_filter = ("service", "date_peremption")
    search_fields = ("produit__nom", "numero_lot")
    date_hierarchy = "date_ajout"
    raw_id_fields = ("produit", "service")


@admin.register(Transfert)
class TransfertAdmin(admin.ModelAdmin):
    list_display = (
        "produit",
        "service_origine",
        "service_destination",
        "quantite_transferee",
        "date_transfert",
    )
    list_filter = ("service_origine", "service_destination", "date_transfert")
    search_fields = ("produit__nom", "numero_lot", "responsable__nom")
    date_hierarchy = "date_transfert"
    raw_id_fields = (
        "produit",
        "service_origine",
        "service_destination",
        "responsable",
    )


