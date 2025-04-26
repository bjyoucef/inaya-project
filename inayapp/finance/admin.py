from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Decharges,
    Payments,
    Tarif_Gardes,
    TarifActe,
    TarifActeConvention,
    Convention,
    HonorairesMedecin,
)
from medical.models.actes import Acte


# Inline for Payments under Decharges
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
    inlines = [PaymentsInline]
    actions = ["export_selected_to_pdf"]

    def export_pdf_link(self, obj):
        if obj.time_export_decharge_pdf:
            return format_html(
                '<a href="/export/decharge/{}/pdf/" target="_blank">PDF</a>', obj.pk
            )
        return "-"

    export_pdf_link.short_description = "Export PDF"

    def export_selected_to_pdf(self, request, queryset):
        # placeholder action
        for obj in queryset:
            obj.time_export_decharge_pdf = timezone.now()
            obj.save()
        self.message_user(request, "PDF export initiated for selected records.")

    export_selected_to_pdf.short_description = "Exporter en PDF"


@admin.register(Tarif_Gardes)
class TarifGardesAdmin(admin.ModelAdmin):
    list_display = ("poste", "service", "shift", "prix", "salaire")
    search_fields = ("poste__name", "service__name")
    list_filter = ("service", "shift")


class TarifActeInline(admin.TabularInline):
    model = TarifActe
    extra = 1


@admin.register(Acte)
class ActeAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "service")
    search_fields = ("code", "libelle")
    inlines = [TarifActeInline]


class TarifConventionInline(admin.TabularInline):
    model = TarifActeConvention
    extra = 1


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "active")
    inlines = [TarifConventionInline]
    search_fields = ("code", "nom")
    list_filter = ("active",)


@admin.register(HonorairesMedecin)
class HonorairesMedecinAdmin(admin.ModelAdmin):
    list_display = ("medecin", "acte", "convention", "montant", "date_effective")
    list_filter = ("medecin", "acte", "convention", "date_effective")
    search_fields = (
        "medecin__user__last_name",
        "medecin__user__first_name",
        "acte__code",
    )
    readonly_fields = ()  # add if needed
    actions = []  # custom actions if any

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("medecin", "acte", "convention")
        )


