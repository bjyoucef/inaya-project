from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count

from pharmacies.models import ConsommationProduit
from .models import (
    Decharges,
    Payments,
    Tarif_Gardes,
    TarifActe,
    TarifActeConvention,
    Convention,
    HonorairesMedecin,
)
from medical.models.actes import Acte, ActeProduit, Prestation, PrestationActe


class PaymentsInline(admin.TabularInline):
    model = Payments
    extra = 0
    readonly_fields = ("time_payment",)


@admin.register(Decharges)
class DechargesAdmin(admin.ModelAdmin):
    list_display = (
        "id_decharge",
        "name",
        "amount",
        "date",
        "created_at",
        "export_pdf_link",
    )
    list_filter = ("date", "created_at", "id_employe")
    search_fields = ("name", "note")
    readonly_fields = ("created_at", "time_export_decharge_pdf")
    inlines = (PaymentsInline,)
    actions = ("export_selected_to_pdf",)

    def export_pdf_link(self, obj):
        if obj.time_export_decharge_pdf:
            return format_html(
                '<a href="/export/decharge/{}/pdf/" target="_blank">PDF</a>', obj.pk
            )
        return "-"

    export_pdf_link.short_description = "Export PDF"

    @admin.action(description="Exporter en PDF")
    def export_selected_to_pdf(self, request, queryset):
        queryset.update(time_export_decharge_pdf=timezone.now())
        self.message_user(request, "PDF export initiated for selected records.")


@admin.register(Tarif_Gardes)
class TarifGardesAdmin(admin.ModelAdmin):
    list_display = ("poste", "service", "shift", "prix", "salaire")
    list_filter = ("service", "shift")
    search_fields = ("poste__name", "service__name")


class TarifActeConventionInline(admin.TabularInline):
    model = TarifActeConvention
    extra = 0
    fields = ("acte", "tarif_acte", "date_effective", "montant_honoraire_base")
    autocomplete_fields = ("acte", "tarif_acte")
    ordering = ("-date_effective",)
    verbose_name_plural = "Configurations tarifaires"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "acte":
            kwargs["queryset"] = Acte.objects.annotate(
                num_tarifs=Count("tarifs")
            ).filter(num_tarifs__gt=0)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "statut", "nombre_actes")
    list_filter = ("active",)
    search_fields = ("code", "nom")
    inlines = (TarifActeConventionInline,)
    actions = (
        "activate_conventions",
        "deactivate_conventions",
    )

    def nombre_actes(self, obj):
        return obj.actes.count()

    nombre_actes.short_description = "Actes associés"

    def statut(self, obj):
        return "Active" if obj.active else "Inactive"

    statut.admin_order_field = "active"
    statut.short_description = "Statut"

    @admin.action(description="Activer les conventions sélectionnées")
    def activate_conventions(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description="Désactiver les conventions sélectionnées")
    def deactivate_conventions(self, request, queryset):
        queryset.update(active=False)


@admin.register(TarifActe)
class TarifActeAdmin(admin.ModelAdmin):
    list_display = ("acte", "montant", "date_effective", "is_default")
    list_filter = ("is_default", "acte__service")
    search_fields = ("acte__code", "montant")
    autocomplete_fields = ("acte",)
    date_hierarchy = "date_effective"


class TarifActeInline(admin.TabularInline):
    model = TarifActe
    extra = 0
    fieldsets = ((None, {"fields": (("montant", "is_default"), ("date_effective",))}),)
    ordering = ("-is_default", "-date_effective")
    verbose_name_plural = "Configurations tarifaires"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("acte")


class ActeProduitInline(admin.TabularInline):
    model = ActeProduit
    extra = 0
    fields = ("produit", "quantite_defaut", "get_unite_mesure")
    readonly_fields = ("get_unite_mesure",)

    def get_unite_mesure(self, obj):
        return obj.produit.get_unite_display()

    get_unite_mesure.short_description = "Unité"


@admin.register(Acte)
class ActeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "libelle",
        "service",
        "tarif_par_defaut",
        "produits_associes",
    )
    list_filter = ("service",)
    search_fields = ("code", "libelle", "service__nom")
    inlines = (TarifActeInline, ActeProduitInline)
    autocomplete_fields = ("service",)
    list_select_related = ("service",)
    list_per_page = 20

    def tarif_par_defaut(self, obj):
        default = obj.tarifs.filter(is_default=True).first()
        return default.montant if default else "-"

    tarif_par_defaut.short_description = "Tarif par défaut"

    def produits_associes(self, obj):
        return obj.produits_defaut.count()

    produits_associes.short_description = "Produits liés"


@admin.register(TarifActeConvention)
class TarifActeConventionAdmin(admin.ModelAdmin):
    list_display = ("convention", "acte", "tarif_acte", "date_effective")
    list_filter = ("convention", "acte")
    search_fields = ("convention__nom", "acte__code")
    raw_id_fields = ("convention", "acte", "tarif_acte")
    date_hierarchy = "date_effective"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("convention", "acte", "tarif_acte")
        )


@admin.register(HonorairesMedecin)
class HonorairesMedecinAdmin(admin.ModelAdmin):
    list_display = ("medecin", "acte", "convention", "montant", "date_effective")
    list_filter = ("convention", "date_effective")
    search_fields = ("medecin__nom", "acte__code")
    autocomplete_fields = ("medecin", "acte", "convention")
    date_hierarchy = "date_effective"
    ordering = ("-date_effective",)


class ConsommationProduitInline(admin.TabularInline):
    model = ConsommationProduit
    extra = 0
    fields = ("produit", "quantite_defaut", "quantite_reelle", "ecart_consommation")
    readonly_fields = ("ecart_consommation",)

    def ecart_consommation(self, obj):
        return obj.quantite_reelle - obj.quantite_defaut

    ecart_consommation.short_description = "Écart"


class PrestationActeInline(admin.TabularInline):
    model = PrestationActe
    extra = 0
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("acte", "convention"),
                    ("tarif_conventionne", "honoraire_medecin"),
                )
            },
        ),
        (
            "Validation",
            {
                "fields": ("convention_accordee", "commentaire"),
                "classes": ("collapse",),
            },
        ),
    )
    inlines = (ConsommationProduitInline,)
    autocomplete_fields = ("acte", "convention")


@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "medecin", "date_prestation", "statut", "total")
    list_filter = ("statut", "date_prestation")
    search_fields = ("patient__nom", "medecin__nom")
    inlines = (PrestationActeInline,)
    date_hierarchy = "date_prestation"
    ordering = ("-date_prestation",)
    list_per_page = 25
    list_select_related = ("patient", "medecin")

    def total(self, obj):
        return obj.prix_total

    total.admin_order_field = "prix_total"


@admin.register(ActeProduit)
class ActeProduitAdmin(admin.ModelAdmin):
    list_display = ("acte", "produit", "quantite_defaut", "service_associe")
    list_filter = ("acte__service",)
    search_fields = ("acte__code", "produit__nom")

    def service_associe(self, obj):
        return obj.acte.service.name

    service_associe.admin_order_field = "acte__service"
    service_associe.short_description = "Service"
