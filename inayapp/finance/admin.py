from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count

from pharmacies.models import ConsommationProduit
from .models import (
    Decharges,
    Payments,
    TarifActe,
    TarifActeConvention,
    Convention,
    HonorairesMedecin,
)
from medical.models.prestation_Kt import ActeKt, ActeProduit, PrestationKt, PrestationActe


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


class TarifActeConventionInline(admin.TabularInline):
    model = TarifActeConvention
    extra = 0
    fields = ("acte", "tarif_acte", "date_effective", "montant_honoraire_base")
    autocomplete_fields = ("acte", "tarif_acte")
    ordering = ("-date_effective",)
    verbose_name_plural = "Configurations tarifaires"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "acte":
            kwargs["queryset"] = ActeKt.objects.annotate(
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


@admin.register(ActeKt)
class ActeKtAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "libelle",
        "service",
        "tarif_par_defaut",
        "produits_associes",
    )
    list_filter = ("service",)
    search_fields = ("code", "libelle", "name")
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


# medical/admin.py

from django.contrib import admin
from .models import PrixSupplementaireConfig
from medecin.models import Medecin


@admin.register(PrixSupplementaireConfig)
class PrixSupplementaireConfigAdmin(admin.ModelAdmin):
    list_display = ("medecin", "pourcentage")
    list_select_related = ("medecin",)
    search_fields = (
        "medecin__personnel__user__first_name",
        "medecin__personnel__user__last_name",
    )
    list_filter = ("pourcentage",)
