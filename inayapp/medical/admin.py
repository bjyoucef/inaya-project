# medical/admin_location.py

from decimal import Decimal

import nested_admin
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.forms import NumberInput, Textarea, TextInput
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from hospitalisations.models import Chambre, Lit

from .models import (ActeKt, ActeProduit, Convention, HonorairesMedecin,
                     PrestationActe, PrestationKt, PrixSupplementaireConfig,
                     TarifActe)
from .models.bloc_location import (ActeLocation, ActeProduitInclus, Bloc,
                                   BlocProduitInclus, ConsommationProduitBloc,
                                   Forfait, ForfaitActeInclus,
                                   ForfaitProduitInclus, LocationBloc,
                                   LocationBlocActe)
from .models.prestation_Kt import (ActeKt, ActeProduit, Convention,
                                   HonorairesMedecin, PrestationActe,
                                   PrestationKt, PrixSupplementaireConfig,
                                   TarifActe)
from .models.services import Service


class LitInline(nested_admin.NestedTabularInline):
    model = Lit
    extra = 0
    fields = ("numero_lit", "est_active", "est_occupe")
    readonly_fields = ("patient_actuel",)  # si v/ous voulez afficher le patient actuel


class ChambreInline(nested_admin.NestedStackedInline):
    model = Chambre
    inlines = [LitInline]
    extra = 0
    fields = (
        "numero_chambre",
        "type_chambre",
        "capacite_lits",
        "prix_nuit",
        "est_active",
        "nombre_lits_occupes",
        "nombre_lits_disponibles",
    )
    readonly_fields = ("nombre_lits_occupes", "nombre_lits_disponibles")


@admin.register(Service)
class ServiceAdmin(nested_admin.NestedModelAdmin):
    list_display = (
        "name",
        "est_hospitalier",
        "est_stockeur",
        "est_pharmacies",
        "total_beds",
        "occupied_beds",
        "occupancy_rate",
    )
    list_filter = ("est_hospitalier", "est_stockeur", "est_pharmacies")
    search_fields = ("name",)
    inlines = [ChambreInline]

    def get_queryset(self, request):
        # précharger chambres + lits pour éviter N+1
        qs = super().get_queryset(request)
        return qs.prefetch_related("chambres__lits")


class ActeProduitInline(admin.TabularInline):
    model = ActeProduit
    extra = 1
    min_num = 0
    autocomplete_fields = ("produit",)
    verbose_name = "Produit par défaut"
    verbose_name_plural = "Produits par défaut"


class TarifActeInline(admin.TabularInline):
    model = TarifActe
    extra = 0
    show_change_link = True
    fields = (
        "convention",
        "montant",
        "montant_honoraire_base",
        "date_effective",
        "is_default",
    )
    readonly_fields = ()
    ordering = ("-is_default", "-date_effective")


@admin.register(ActeKt)
class ActeKtAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "service", "nombre_produits_defaut")
    search_fields = ("code", "libelle", "service__nom")
    list_filter = ("service",)
    inlines = (ActeProduitInline, TarifActeInline)
    ordering = ("code",)

    def nombre_produits_defaut(self, obj):
        return obj.produits_defaut.count()

    nombre_produits_defaut.short_description = "Nb. produits par défaut"

@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "active")
    search_fields = ("code", "nom")
    list_filter = ("active",)


# medical/admin.py


# Inline for BlocProduitInclus in Bloc
class BlocProduitInclusInline(admin.TabularInline):
    model = BlocProduitInclus
    extra = 1  # Nombre de formulaires vides supplémentaires
    fk_name = "bloc"  # Spécifie la clé étrangère si nécessaire


@admin.register(Bloc)
class BlocAdmin(admin.ModelAdmin):
    list_display = ("nom_bloc", "prix_base", "prix_supplement_30min", "est_active")
    search_fields = ("nom_bloc",)
    inlines = [BlocProduitInclusInline]


# Inline for ForfaitProduitInclus in Forfait
class ForfaitProduitInclusInline(admin.TabularInline):
    model = ForfaitProduitInclus
    extra = 1
    fk_name = "forfait"


# Inline for ForfaitActeInclus in Forfait
class ForfaitActeInclusInline(admin.TabularInline):
    model = ForfaitActeInclus
    extra = 1
    fk_name = "forfait"


@admin.register(Forfait)
class ForfaitAdmin(admin.ModelAdmin):
    list_display = ("nom", "prix", "duree", "est_active")
    search_fields = ("nom",)
    inlines = [ForfaitProduitInclusInline, ForfaitActeInclusInline]


# Inline for ActeProduitInclus in ActeLocation
class ActeProduitInclusInline(admin.TabularInline):
    model = ActeProduitInclus
    extra = 1
    fk_name = "acte"


@admin.register(ActeLocation)
class ActeLocationAdmin(admin.ModelAdmin):
    list_display = ("nom", "prix", "duree_estimee", "est_active")
    search_fields = ("nom",)
    inlines = [ActeProduitInclusInline]
