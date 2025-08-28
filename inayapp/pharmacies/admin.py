from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone

from pharmacies.models import Produit


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("nom", "code_produit", "prix_vente", "est_active")
    list_filter = ("est_active",)
    search_fields = ("nom", "code_produit")
    list_editable = ("prix_vente", "est_active")
