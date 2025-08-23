from django.contrib import admin
from django.db.models import BooleanField, Case, When
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
from medecin.models import Medecin
from patients.models import Patient
from pharmacies.models import Produit
from django.utils import timezone

from .models import Service
from .models.bloc_location import (
    ActeLocation, ActeProduitInclus, Bloc,
                                   BlocProduitInclus, ConsommationProduitBloc,
    Forfait, ForfaitProduitInclus, ForfaitActeInclus,
    LocationBloc, LocationBlocActe, LocationBlocAudit
)
from .models.prestation_Kt import (
    ActeKt, ActeProduit, PrestationActe,
    PrestationAudit, PrestationKt
)
from .resources import (
    ActeLocationResource, BlocResource, ForfaitResource,
                        LocationBlocResource, PrestationKtResource,
    ServiceResource
)


class BlocProduitInclusInline(admin.TabularInline):
    model = BlocProduitInclus
    extra = 1
    fields = ("produit", "quantite")
    autocomplete_fields = ("produit",)


class ForfaitProduitInclusInline(admin.TabularInline):
    model = ForfaitProduitInclus
    extra = 1
    fields = ("produit", "quantite")
    autocomplete_fields = ("produit",)


class ForfaitActeInclusInline(admin.TabularInline):
    model = ForfaitActeInclus
    extra = 1
    fields = ("acte", "quantite", "prix_unitaire_inclus")
    autocomplete_fields = ("acte",)


class ActeProduitInclusInline(admin.TabularInline):
    model = ActeProduitInclus
    extra = 1
    fields = ("produit", "quantite_standard", "est_obligatoire")
    autocomplete_fields = ("produit",)


class LocationBlocActeInline(admin.TabularInline):
    model = LocationBlocActe
    extra = 1
    fields = ("acte", "quantite", "prix_unitaire", "prix_total")
    autocomplete_fields = ("acte",)
    readonly_fields = ("prix_total",)


class ConsommationProduitBlocInline(admin.TabularInline):
    model = ConsommationProduitBloc
    extra = 1
    fields = (
        "produit",
        "quantite",
        "prix_unitaire",
        "montant_total",
        "est_inclus",
        "source_inclusion",
    )
    autocomplete_fields = ("produit",)
    readonly_fields = ("montant_total",)

    def montant_total(self, obj):
        """
        Retourne la valeur calculée (quantite * prix_unitaire).
        S'assure de gérer les cas où l'objet n'est pas encore sauvegardé ou
        où les valeurs sont None.
        """
        if not obj or (
            obj.pk is None and (obj.quantite is None and obj.prix_unitaire is None)
        ):
            return ""  # vide pour les lignes vierges/creation inline
        try:
            q = obj.quantite or 0
            p = obj.prix_unitaire or 0
            total = q * p
        except Exception:
            return ""
        # formater selon votre préférence ; ici 2 décimales
        return f"{total:.2f}"

    montant_total.short_description = "Montant total"


class PrestationActeInline(admin.TabularInline):
    model = PrestationActe
    extra = 1
    fields = (
        "acte",
        "convention",
        "tarif_conventionne",
        "convention_accordee",
        "honoraire_medecin",
        "commentaire",
    )
    autocomplete_fields = ("acte", "convention")
    readonly_fields = ("tarif_conventionne", "honoraire_medecin")


# Custom List Filters
class BlocListFilter(admin.SimpleListFilter):
    title = "Type de bloc"
    parameter_name = "type_bloc"

    def lookups(self, request, model_admin):
        return (
            ("cher", "Blocs premium (>20000 DA)"),
            ("standard", "Blocs standard (10000-20000 DA)"),
            ("economique", "Blocs économiques (<10000 DA)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "cher":
            return queryset.filter(prix_base__gt=20000)
        if self.value() == "standard":
            return queryset.filter(prix_base__gte=10000, prix_base__lte=20000)
        if self.value() == "economique":
            return queryset.filter(prix_base__lt=10000)


class ForfaitDureeFilter(admin.SimpleListFilter):
    title = "Durée du forfait"
    parameter_name = "duree_forfait"

    def lookups(self, request, model_admin):
        return (
            ("court", "Court (<2h)"),
            ("moyen", "Moyen (2h-4h)"),
            ("long", "Long (>4h)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "court":
            return queryset.filter(duree__lt=120)
        if self.value() == "moyen":
            return queryset.filter(duree__gte=120, duree__lte=240)
        if self.value() == "long":
            return queryset.filter(duree__gt=240)


class LocationBlocDateFilter(admin.SimpleListFilter):
    title = "Période d'opération"
    parameter_name = "date_operation"

    def lookups(self, request, model_admin):
        return (
            ("today", "Aujourd'hui"),
            ("week", "Cette semaine"),
            ("month", "Ce mois"),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()
        if self.value() == "today":
            return queryset.filter(date_operation=today)
        if self.value() == "week":
            start_week = today - timezone.timedelta(days=today.weekday())
            end_week = start_week + timezone.timedelta(days=6)
            return queryset.filter(date_operation__range=[start_week, end_week])
        if self.value() == "month":
            return queryset.filter(
                date_operation__year=today.year, date_operation__month=today.month
            )


# Admin Configurations
@admin.register(Service)
class ServiceAdmin(ImportExportModelAdmin):
    resource_class = ServiceResource
    list_display = (
        "name",
        "color",
        "est_stockeur",
        "est_pharmacies",
        "est_hospitalier",
        "actes_count",
    )
    list_filter = ("est_stockeur", "est_pharmacies", "est_hospitalier")
    search_fields = ("name",)
    list_editable = ("color", "est_stockeur", "est_pharmacies", "est_hospitalier")

    def actes_count(self, obj):
        return obj.actes.count()

    actes_count.short_description = "Nombre d'actes"


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("nom", "code_produit", "prix_vente", "stock_total")
    search_fields = ("nom", "code_produit")
    list_filter = ("est_actif",)

    def stock_total(self, obj):
        return sum(stock.quantite for stock in obj.stocks.all())

    stock_total.short_description = "Stock total"


@admin.register(Bloc)
class BlocAdmin(ImportExportModelAdmin):
    resource_class = BlocResource
    list_display = (
        "nom_bloc",
        "prix_base",
        "prix_supplement_30min",
        "est_actif",
        "nombre_locations",
        "exemple_calcul_prix",
    )
    list_filter = ("est_actif", BlocListFilter)
    search_fields = ("nom_bloc", "description")
    list_editable = ("est_actif", "prix_base", "prix_supplement_30min")
    readonly_fields = ("exemple_calcul_prix",)
    fieldsets = (
        (
            "Informations générales",
            {"fields": ("nom_bloc", "description", "est_actif")},
        ),
        (
            "Tarification",
            {"fields": ("prix_base", "prix_supplement_30min", "exemple_calcul_prix")},
        ),
    )
    inlines = [BlocProduitInclusInline]  # Use list syntax for clarity

    def nombre_locations(self, obj):
        return obj.locations.count()

    nombre_locations.short_description = "Nombre de locations"

    def exemple_calcul_prix(self, obj):
        if obj.pk:
            exemples = []
            durees = [90, 120, 180, 240]
            for duree in durees:
                prix = obj.calculer_prix_location(duree)
                heures = duree // 60
                minutes = duree % 60
                duree_str = f"{heures}h{minutes:02d}" if minutes else f"{heures}h"
                exemples.append(f"{duree_str}: {prix:,.2f} DA")
            return format_html("<br>".join(exemples))
        return "Sauvegardez d'abord pour voir les exemples"

    exemple_calcul_prix.short_description = "Exemples de prix"


@admin.register(Forfait)
class ForfaitAdmin(ImportExportModelAdmin):
    resource_class = ForfaitResource
    list_display = (
        "nom",
        "prix",
        "duree",
        "duree_formatted",
        "nombre_produits",
        "nombre_actes",
        "est_actif",
        "nombre_locations",
    )
    list_filter = ("est_actif", ForfaitDureeFilter, "date_creation")
    search_fields = ("nom", "description")
    list_editable = ("est_actif", "prix", "duree")
    inlines = [ForfaitProduitInclusInline, ForfaitActeInclusInline]
    date_hierarchy = "date_creation"
    fieldsets = (
        ("Informations générales", {"fields": ("nom", "description", "est_actif")}),
        ("Tarification", {"fields": ("prix", "duree")}),
        (
            "Métadonnées",
            {
                "fields": ("date_creation", "date_modification"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("date_creation", "date_modification")
    actions = ("activer_forfaits", "desactiver_forfaits")

    def duree_formatted(self, obj):
        heures = obj.duree // 60
        minutes = obj.duree % 60
        return f"{heures}h{minutes:02d}" if heures > 0 else f"{minutes}min"

    duree_formatted.short_description = "Durée"

    def nombre_produits(self, obj):
        return obj.produits.count()

    nombre_produits.short_description = "Produits inclus"

    def nombre_actes(self, obj):
        return obj.actes_inclus.count()

    nombre_actes.short_description = "Actes inclus"

    def nombre_locations(self, obj):
        return obj.locations.count()

    nombre_locations.short_description = "Locations"

    def activer_forfaits(self, request, queryset):
        queryset.update(est_actif=True)
        self.message_user(request, "Les forfaits sélectionnés ont été activés.")

    activer_forfaits.short_description = "Activer les forfaits"

    def desactiver_forfaits(self, request, queryset):
        queryset.update(est_actif=False)
        self.message_user(request, "Les forfaits sélectionnés ont été désactivés.")

    desactiver_forfaits.short_description = "Désactiver les forfaits"


@admin.register(ActeLocation)
class ActeLocationAdmin(ImportExportModelAdmin):
    resource_class = ActeLocationResource
    list_display = ("nom", "prix", "duree_estimee", "est_actif", "nombre_locations", "nombre_produits_inclus")
    list_filter = ("est_actif", "date_creation")
    search_fields = ("nom", "description")
    list_editable = ("est_actif", "prix", "duree_estimee")
    inlines = [ActeProduitInclusInline]
    date_hierarchy = "date_creation"
    fieldsets = (
        ("Informations générales", {"fields": ("nom", "description", "est_actif")}),
        ("Détails", {"fields": ("prix", "duree_estimee")}),
        (
            "Métadonnées",
            {
                "fields": ("date_creation", "date_modification"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("date_creation", "date_modification")

    def nombre_locations(self, obj):
        return obj.locations.count()

    nombre_locations.short_description = "Nombre de locations"

    def nombre_produits_inclus(self, obj):
        return obj.produits_inclus.count()

    nombre_produits_inclus.short_description = "Produits inclus"


@admin.register(LocationBloc)
class LocationBlocAdmin(ImportExportModelAdmin):
    resource_class = LocationBlocResource
    list_display = (
        "nom_acte",
        "bloc",
        "patient",
        "medecin",
        "date_operation",
        "heure_operation",
        "type_tarification",
        "forfait",
        "duree_reelle",
        "prix_final",
        "montant_total_facture",
        "view_details",
        "montant_paye_caisse",
        "statut_paiement_display",
        "reglement_status",
    )
    list_filter = (
        "statut_paiement",
        "type_tarification",
        "bloc",
        "medecin",
        LocationBlocDateFilter,
        "date_operation",
        "bloc",
        "date_reglement_surplus",
        "date_reglement_complement",
    )
    search_fields = (
        "nom_acte",
        "patient__first_name",  # Updated to use correct field
        "patient__last_name",  # Updated to use correct field
        "medecin__nom_complet",  # Updated to use property
        "bloc__nom_bloc",
        "forfait__nom",
    )
    list_editable = ("duree_reelle",)
    date_hierarchy = "date_operation"
    inlines = [LocationBlocActeInline, ConsommationProduitBlocInline]
    fieldsets = (
        (
            "Informations principales",
            {"fields": ("bloc", "patient", "medecin", "nom_acte")},
        ),
        (
            "Détails de l'opération",
            {"fields": ("date_operation", "heure_operation", "duree_reelle")},
        ),
        (
            "Tarification",
            {
                "fields": (
                    "type_tarification",
                    "forfait",
                    "prix_final",
                    "prix_supplement_duree",
                    "montant_total_facture",
                )
            },
        ),
        (
            "Paiements",
            {
                "fields": (
                    "montant_paye_caisse",
                    "difference_paiement",
                    "statut_paiement",
                    "surplus_a_verser",
                    "complement_du_medecin",
                    "notes_paiement",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Règlements",
            {
                "fields": (
                    "date_reglement_surplus",
                    "date_reglement_complement",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Observations", {"fields": ("observations",)}),
        (
            "Métadonnées",
            {
                "fields": ("date_creation", "date_modification", "cree_par"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = (
        "date_creation",
        "date_modification",
        "prix_final",
        "montant_total_facture",
    )
    autocomplete_fields = ("bloc", "patient", "medecin", "forfait")
    actions = ("recalculer_prix", "marquer_surplus_verse", "marquer_complement_paye")

    def view_details(self, obj):
        url = reverse("admin:medical_locationbloc_change", args=[obj.id])
        return format_html('<a href="{}" class="btn btn-sm btn-primary">Voir</a>', url)

    view_details.short_description = "Détails"

    def statut_paiement_display(self, obj):
        """Affichage coloré du statut de paiement"""
        statut_colors = {
            "EQUILIBRE": "success",
            "SURPLUS_CLINIQUE": "info",
            "COMPLEMENT_MEDECIN": "warning",
            "AUCUN_PAIEMENT": "secondary",
        }
        color = statut_colors.get(obj.statut_paiement, "secondary")
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            obj.get_statut_paiement_display(),
        )

    statut_paiement_display.short_description = "Statut paiement"

    def reglement_status(self, obj):
        """Affichage du statut des règlements"""
        if obj.statut_paiement == "EQUILIBRE":
            return format_html('<span class="badge bg-success">Équilibré</span>')
        elif obj.statut_paiement == "AUCUN_PAIEMENT":
            return format_html('<span class="badge bg-secondary">N/A</span>')
        elif obj.statut_paiement == "SURPLUS_CLINIQUE":
            if obj.date_reglement_surplus:
                return format_html(
                    '<span class="badge bg-success">Versé le {}</span>',
                    obj.date_reglement_surplus.strftime("%d/%m/%Y"),
                )
            else:
                return format_html(
                    '<span class="badge bg-danger">À verser ({} DA)</span>',
                    obj.surplus_a_verser,
                )
        elif obj.statut_paiement == "COMPLEMENT_MEDECIN":
            if obj.date_reglement_complement:
                return format_html(
                    '<span class="badge bg-success">Payé le {}</span>',
                    obj.date_reglement_complement.strftime("%d/%m/%Y"),
                )
            else:
                return format_html(
                    '<span class="badge bg-warning">À recevoir ({} DA)</span>',
                    obj.complement_du_medecin,
                )
        return format_html('<span class="badge bg-secondary">-</span>')

    reglement_status.short_description = "Règlements"

    def marquer_surplus_verse(self, request, queryset):
        """Action pour marquer les surplus comme versés"""
        from django.utils import timezone

        count = 0
        for location in queryset.filter(
            statut_paiement="SURPLUS_CLINIQUE", date_reglement_surplus__isnull=True
        ):
            location.date_reglement_surplus = timezone.localdate()
            location.save()
            count += 1

        self.message_user(request, f"{count} surplus marqués comme versés")

    marquer_surplus_verse.short_description = (
        "Marquer les surplus sélectionnés comme versés"
    )

    def marquer_complement_paye(self, request, queryset):
        """Action pour marquer les compléments comme payés"""
        from django.utils import timezone

        count = 0
        for location in queryset.filter(
            statut_paiement="COMPLEMENT_MEDECIN", date_reglement_complement__isnull=True
        ):
            location.date_reglement_complement = timezone.localdate()
            location.save()
            count += 1

        self.message_user(request, f"{count} compléments marqués comme payés")

    marquer_complement_paye.short_description = (
        "Marquer les compléments sélectionnés comme payés"
    )

    def recalculer_prix(self, request, queryset):
        for location in queryset:
            location.save()  # Triggers automatic price recalculation
        self.message_user(
            request, "Les prix des locations sélectionnées ont été recalculés."
        )

    recalculer_prix.short_description = "Recalculer les prix"


@admin.register(PrestationKt)
class PrestationKtAdmin(ImportExportModelAdmin):
    resource_class = PrestationKtResource
    list_display = (
        "id",
        "patient",
        "medecin",
        "date_prestation",
        "statut",
        "prix_total",
        "stock_impact_applied",
        "view_details",
    )
    list_filter = ("statut", "medecin", "date_prestation")
    search_fields = (
        "patient__first_name",  # Updated to use correct field
        "patient__last_name",  # Updated to use correct field
        "medecin__nom_complet",  # Updated to use property
    )
    date_hierarchy = "date_prestation"
    inlines = [PrestationActeInline]
    fieldsets = (
        (
            "Informations principales",
            {"fields": ("patient", "medecin", "date_prestation", "statut")},
        ),
        (
            "Tarification",
            {
                "fields": (
                    "prix_total",
                    "prix_supplementaire",
                    "prix_supplementaire_medecin",
                )
            },
        ),
        ("Observations", {"fields": ("observations",)}),
        ("Stock", {"fields": ("stock_impact_applied",)}),
    )
    readonly_fields = ("prix_total", "stock_impact_applied")
    autocomplete_fields = ("patient", "medecin")
    actions = ("apply_stock_impact", "revert_stock_impact", "update_total_price")

    def view_details(self, obj):
        url = reverse("admin:medical_prestationkt_change", args=[obj.id])
        return format_html('<a href="{}" class="btn btn-sm btn-primary">Voir</a>', url)

    view_details.short_description = "Détails"

    def apply_stock_impact(self, request, queryset):
        for prestation in queryset:
            prestation.apply_stock_impact()
        self.message_user(
            request,
            "L'impact sur le stock a été appliqué pour les prestations sélectionnées.",
        )

    apply_stock_impact.short_description = "Appliquer l'impact stock"

    def revert_stock_impact(self, request, queryset):
        for prestation in queryset:
            prestation.revert_stock_impact()
        self.message_user(
            request,
            "L'impact sur le stock a été annulé pour les prestations sélectionnées.",
        )

    revert_stock_impact.short_description = "Annuler l'impact stock"

    def update_total_price(self, request, queryset):
        for prestation in queryset:
            prestation.update_total_price()
        self.message_user(
            request,
            "Les prix totaux ont été mis à jour pour les prestations sélectionnées.",
        )

    update_total_price.short_description = "Mettre à jour les prix totaux"


@admin.register(PrestationAudit)
class PrestationAuditAdmin(admin.ModelAdmin):
    list_display = (
        "prestation",
        "user",
        "champ",
        "ancienne_valeur",
        "nouvelle_valeur",
        "date_modification",
    )
    list_filter = ("champ", "date_modification", "user")
    search_fields = ("prestation__id", "champ", "ancienne_valeur", "nouvelle_valeur")
    date_hierarchy = "date_modification"
    readonly_fields = (
        "prestation",
        "user",
        "champ",
        "ancienne_valeur",
        "nouvelle_valeur",
        "date_modification",
    )
    list_per_page = 50


@admin.register(LocationBlocAudit)
class LocationBlocAuditAdmin(admin.ModelAdmin):
    list_display = (
        "location",
        "user",
        "champ",
        "ancienne_valeur",
        "nouvelle_valeur",
        "date_modification",
    )
    list_filter = ("champ", "date_modification", "user")
    search_fields = (
        "location__nom_acte",
        "champ",
        "ancienne_valeur",
        "nouvelle_valeur",
    )
    date_hierarchy = "date_modification"
    readonly_fields = (
        "location",
        "user",
        "champ",
        "ancienne_valeur",
        "nouvelle_valeur",
        "date_modification",
    )
    list_per_page = 50


@admin.register(ForfaitActeInclus)
class ForfaitActeInclusAdmin(admin.ModelAdmin):
    list_display = ("forfait", "acte", "quantite", "prix_unitaire_inclus")
    list_filter = ("forfait",)
    search_fields = ("forfait__nom", "acte__nom")
    autocomplete_fields = ("forfait", "acte")


@admin.register(ActeProduitInclus)
class ActeProduitInclusAdmin(admin.ModelAdmin):
    list_display = ("acte", "produit", "quantite_standard", "est_obligatoire")
    list_filter = ("est_obligatoire", "acte")
    search_fields = ("acte__nom", "produit__nom")
    autocomplete_fields = ("acte", "produit")


@admin.register(LocationBlocActe)
class LocationBlocActeAdmin(admin.ModelAdmin):
    list_display = ("location", "acte", "quantite", "prix_unitaire", "prix_total")
    list_filter = ("location",)
    search_fields = ("location__nom_acte", "acte__nom")
    autocomplete_fields = ("location", "acte")
    readonly_fields = ("prix_total",)


@admin.register(ConsommationProduitBloc)
class ConsommationProduitBlocAdmin(admin.ModelAdmin):
    list_display = (
        "location",
        "produit",
        "quantite",
        "prix_unitaire",
        "prix_total",
        "source_inclusion",
        "est_inclus",
        "prix_total_utilise",
    )
    list_filter = ("source_inclusion", "est_inclus", "location")
    search_fields = ("location__nom_acte", "produit__nom")
    autocomplete_fields = ("location", "produit", "acte_associe")
    readonly_fields = [
        "prix_total_utilise",  # instead of 'prix_total'
        "prix_total_inclus",  # instead of 'prix_inclus'
        "montant_supplement",  # instead of 'prix_ecart'
        "montant_supplement",  # instead of 'prix_facturable' (or create separate property)
        "montant_economie",  # instead of 'economie'
    ]

@admin.register(BlocProduitInclus)
class BlocProduitInclusAdmin(admin.ModelAdmin):
    list_display = ("bloc", "produit", "quantite")
    list_filter = ("bloc",)
    search_fields = ("bloc__nom_bloc", "produit__nom")
    autocomplete_fields = ("bloc", "produit")


@admin.register(ForfaitProduitInclus)
class ForfaitProduitInclusAdmin(admin.ModelAdmin):
    list_display = ("forfait", "produit", "quantite")
    list_filter = ("forfait",)
    search_fields = ("forfait__nom", "produit__nom")
    autocomplete_fields = ("forfait", "produit")


# Admin Site Customization
admin.site.site_header = "Administration Médicale"
admin.site.site_title = "Admin Médical"
admin.site.index_title = "Gestion des Prestations et Locations de Bloc"
