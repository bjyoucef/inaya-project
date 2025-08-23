from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count
from datetime import timedelta, datetime
from .models import (
    Personnel,
    Planning,
    PointagesActes,
    Poste,
    HonorairesActe,
    Shift,
    SalaryAdvanceRequest,
    LeaveRequest,
    Tarif_Gardes,
)


# ─── Mixins pour fonctionnalités communes ────────────────────────────────────
class ReadOnlyMixin:
    """Mixin pour rendre certains champs en lecture seule"""

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Édition
            return self.readonly_fields + ("created_at", "updated_at")
        return self.readonly_fields


class ExportMixin:
    """Mixin pour l'export CSV"""

    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={meta}.csv"

        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Exporter en CSV"



class SalaryAdvanceRequestInline(admin.TabularInline):
    model = SalaryAdvanceRequest
    extra = 0
    fields = ("amount", "request_date", "payment_date", "status", "colored_status")
    readonly_fields = ("created_at", "updated_at", "colored_status")
    date_hierarchy = "request_date"

    def colored_status(self, obj):
        colors = {
            "PENDING": "orange",
            "APPROVED": "green",
            "REJECTED": "red",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "black"),
            obj.get_status_display(),
        )

    colored_status.short_description = "Statut"


class LeaveRequestInline(admin.TabularInline):
    model = LeaveRequest
    extra = 0
    fields = (
        "start_date",
        "end_date",
        "leave_type",
        "status",
        "duration_days",
        "colored_status",
    )
    readonly_fields = ("created_at", "updated_at", "duration_days", "colored_status")
    date_hierarchy = "start_date"

    def duration_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return "-"

    duration_days.short_description = "Durée (jours)"

    def colored_status(self, obj):
        colors = {
            "PENDING": "orange",
            "APPROVED": "green",
            "REJECTED": "red",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "black"),
            obj.get_status_display(),
        )

    colored_status.short_description = "Statut"


# ─── Personnel Admin Amélioré ─────────────────────────────────────────────────
@admin.register(Personnel)
class PersonnelAdmin(ReadOnlyMixin, ExportMixin, admin.ModelAdmin):
    list_display = (
        "nom_prenom",
        "poste",
        "service",
        "telephone",
        "salaire_formatted",
        "activity_status",
        "advance_status",
        "actions_links",
    )
    search_fields = ("nom_prenom", "telephone", "poste__label")
    list_filter = (
        "poste",
        "service",
        "statut_activite",
        "use_in_planning",
        "salary_advance_request",
    )
    date_hierarchy = "created_at"
    ordering = ("nom_prenom",)
    inlines = [SalaryAdvanceRequestInline, LeaveRequestInline]
    raw_id_fields = ("user", "employee")
    readonly_fields = ("created_at", "updated_at", "taux_horaire", "stats_summary")
    actions = ["export_as_csv", "activate_personnel", "deactivate_personnel"]

    fieldsets = (
        ("Informations personnelles", {"fields": ("nom_prenom", "telephone", "user")}),
        (
            "Informations professionnelles",
            {"fields": ("poste", "service", "salaire", "taux_horaire", "employee")},
        ),
        (
            "Statuts",
            {
                "fields": (
                    "statut_activite",
                    "use_in_planning",
                    "salary_advance_request",
                )
            },
        ),
        ("Statistiques", {"fields": ("stats_summary",), "classes": ("collapse",)}),
        (
            "Métadonnées",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def salaire_formatted(self, obj):
        return f"{obj.salaire} €" if obj.salaire else "Non défini"

    salaire_formatted.short_description = "Salaire"
    salaire_formatted.admin_order_field = "salaire"

    def activity_status(self, obj):
        if obj.statut_activite:
            return format_html('<span style="color: green;">✓ Actif</span>')
        return format_html('<span style="color: red;">✗ Inactif</span>')

    activity_status.short_description = "Activité"
    activity_status.admin_order_field = "statut_activite"


    def advance_status(self, obj):
        if obj.salary_advance_request:
            return format_html('<span style="color: orange;">⚠ Demande en cours</span>')
        return format_html('<span style="color: green;">✓ OK</span>')

    advance_status.short_description = "Avance"
    advance_status.admin_order_field = "salary_advance_request"

    def actions_links(self, obj):
        """Liens rapides vers les actions"""
        links = []

        # Lien vers les demandes d'avance
        advance_url = (
            reverse("admin:rh_salaryadvancerequest_changelist")
            + f"?personnel__id__exact={obj.id}"
        )
        links.append(f'<a href="{advance_url}">Avances</a>')

        # Lien vers les congés
        leave_url = (
            reverse("admin:rh_leaverequest_changelist")
            + f"?personnel__id__exact={obj.id}"
        )
        links.append(f'<a href="{leave_url}">Congés</a>')

        return format_html(" | ".join(links))

    actions_links.short_description = "Actions"

    def stats_summary(self, obj):
        """Résumé des statistiques de l'employé"""
        if not obj.pk:
            return "Aucune statistique disponible"

        # Plannings ce mois
        current_month = timezone.now().date().replace(day=1)
        next_month = (current_month + timedelta(days=32)).replace(day=1)

        plannings_count = Planning.objects.filter(
            employee=obj, shift_date__gte=current_month, shift_date__lt=next_month
        ).count()

        # Revenus ce mois
        revenus = (
            Planning.objects.filter(
                employee=obj, shift_date__gte=current_month, shift_date__lt=next_month
            ).aggregate(total=Sum("paiement"))["total"]
            or 0
        )

        # Demandes d'avance en attente
        pending_advances = SalaryAdvanceRequest.objects.filter(
            personnel=obj, status="PENDING"
        ).count()

        return format_html(
            "<strong>Ce mois:</strong> {} plannings, {} € de revenus<br>"
            "<strong>Avances en attente:</strong> {}",
            plannings_count,
            revenus,
            pending_advances,
        )

    stats_summary.short_description = "Statistiques"

    def activate_personnel(self, request, queryset):
        updated = queryset.update(statut_activite=True)
        self.message_user(request, f"{updated} employé(s) activé(s).")

    activate_personnel.short_description = "Activer les employés sélectionnés"

    def deactivate_personnel(self, request, queryset):
        updated = queryset.update(statut_activite=False)
        self.message_user(request, f"{updated} employé(s) désactivé(s).")

    deactivate_personnel.short_description = "Désactiver les employés sélectionnés"


# ─── Planning Admin Amélioré ──────────────────────────────────────────────────
class PointagesActesInline(admin.TabularInline):
    model = PointagesActes
    extra = 0
    fields = ("acte", "nbr_actes", "total_price")
    raw_id_fields = ("acte",)
    readonly_fields = ("total_price",)

    def total_price(self, obj):
        if obj.acte and obj.nbr_actes:
            total = obj.acte.prix_acte * obj.nbr_actes
            return f"{total} €"
        return "-"

    total_price.short_description = "Total"



# ─── Inline pour les actes honoraires dans Poste ───────────────────────────────
class HonorairesActeInline(admin.TabularInline):
    model = HonorairesActe
    extra = 0
    fields = ("name_acte", "prix_acte")
    show_change_link = True


# ─── Autres modèles améliorés ─────────────────────────────────────────────────
@admin.register(Poste)
class PosteAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ("label", "personnel_count", "acts_count")
    search_fields = ("label",)
    inlines = [HonorairesActeInline]
    actions = ["export_as_csv"]

    def personnel_count(self, obj):
        count = obj.personnel_set.count()
        return f"{count} employé(s)"

    personnel_count.short_description = "Employés"

    def acts_count(self, obj):
        count = obj.honorairesacte_set.count()
        return f"{count} acte(s)"

    acts_count.short_description = "Actes disponibles"


@admin.register(HonorairesActe)
class HonorairesActeAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ("name_acte", "prix_acte_formatted", "poste", "usage_stats")
    search_fields = ("name_acte",)
    list_filter = ("poste",)
    raw_id_fields = ("poste",)
    actions = ["export_as_csv"]

    def prix_acte_formatted(self, obj):
        return f"{obj.prix_acte} €"

    prix_acte_formatted.short_description = "Prix"
    prix_acte_formatted.admin_order_field = "prix_acte"

    def usage_stats(self, obj):
        """Statistiques d'utilisation de l'acte"""
        count = PointagesActes.objects.filter(acte=obj).count()
        total = (
            PointagesActes.objects.filter(acte=obj).aggregate(total=Sum("nbr_actes"))[
                "total"
            ]
            or 0
        )
        return f"{count} utilisations, {total} actes"

    usage_stats.short_description = "Utilisation"


@admin.register(Shift)
class ShiftAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ("code", "label", "time_range", "planning_count")
    search_fields = ("code", "label")
    list_filter = ("debut", "fin")
    actions = ["export_as_csv"]

    def time_range(self, obj):
        if obj.debut and obj.fin:
            return f"{obj.debut} - {obj.fin}"
        return "Non défini"

    time_range.short_description = "Horaires"

    def planning_count(self, obj):
        count = obj.planning_set.count()
        return f"{count} planning(s)"

    planning_count.short_description = "Utilisations"


@admin.register(Tarif_Gardes)
class TarifGardesAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ("poste", "service", "shift", "prix_formatted", "salaire_formatted")
    list_filter = ("service", "shift", "poste")
    search_fields = ("poste__label", "service__name")
    actions = ["export_as_csv"]

    def prix_formatted(self, obj):
        return f"{obj.prix} €" if obj.prix else "Non défini"

    prix_formatted.short_description = "Prix"
    prix_formatted.admin_order_field = "prix"

    def salaire_formatted(self, obj):
        return f"{obj.salaire} €" if obj.salaire else "Non défini"

    salaire_formatted.short_description = "Salaire"
    salaire_formatted.admin_order_field = "salaire"


@admin.register(SalaryAdvanceRequest)
class SalaryAdvanceRequestAdmin(ReadOnlyMixin, ExportMixin, admin.ModelAdmin):
    list_display = (
        "personnel_link",
        "amount_formatted",
        "request_date",
        "payment_date",
        "colored_status",
        "days_pending",
    )
    search_fields = ("personnel__nom_prenom",)
    list_filter = ("status", "request_date", "payment_date")
    date_hierarchy = "request_date"
    raw_id_fields = ("personnel",)
    readonly_fields = ("created_at", "updated_at", "days_pending_detail")
    actions = ["export_as_csv", "approve_requests", "reject_requests"]

    fieldsets = (
        ("Demande", {"fields": ("personnel", "amount", "reason")}),
        ("Dates", {"fields": ("request_date", "payment_date", "days_pending_detail")}),
        ("Statut", {"fields": ("status",)}),
        (
            "Métadonnées",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def personnel_link(self, obj):
        url = reverse("admin:rh_personnel_change", args=[obj.personnel.id])
        return format_html('<a href="{}">{}</a>', url, obj.personnel.nom_prenom)

    personnel_link.short_description = "Employé"
    personnel_link.admin_order_field = "personnel__nom_prenom"

    def amount_formatted(self, obj):
        return f"{obj.amount} €"

    amount_formatted.short_description = "Montant"
    amount_formatted.admin_order_field = "amount"

    def colored_status(self, obj):
        colors = {
            "PENDING": ("orange", "⏳"),
            "APPROVED": ("green", "✓"),
            "REJECTED": ("red", "✗"),
        }
        color, icon = colors.get(obj.status, ("black", "?"))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_status_display(),
        )

    colored_status.short_description = "Statut"
    colored_status.admin_order_field = "status"

    def days_pending(self, obj):
        if obj.status == "PENDING" and obj.request_date:
            days = (timezone.now().date() - obj.request_date).days
            color = "red" if days > 7 else "orange" if days > 3 else "green"
            return format_html('<span style="color: {};">{} jours</span>', color, days)
        return "-"

    days_pending.short_description = "En attente depuis"

    def days_pending_detail(self, obj):
        if obj.status == "PENDING" and obj.request_date:
            days = (timezone.now().date() - obj.request_date).days
            return f"{days} jours"
        return "Non applicable"

    days_pending_detail.short_description = "Jours en attente"

    def approve_requests(self, request, queryset):
        updated = queryset.filter(status="PENDING").update(
            status="APPROVED", payment_date=timezone.now().date()
        )
        self.message_user(request, f"{updated} demande(s) approuvée(s).")

    approve_requests.short_description = "Approuver les demandes"

    def reject_requests(self, request, queryset):
        updated = queryset.filter(status="PENDING").update(status="REJECTED")
        self.message_user(request, f"{updated} demande(s) rejetée(s).")

    reject_requests.short_description = "Rejeter les demandes"


@admin.register(LeaveRequest)
class LeaveRequestAdmin(ReadOnlyMixin, ExportMixin, admin.ModelAdmin):
    list_display = (
        "personnel_link",
        "leave_type",
        "start_date",
        "end_date",
        "duration_days",
        "colored_status",
        "urgency_indicator",
    )
    search_fields = ("personnel__nom_prenom",)
    list_filter = ("leave_type", "status", "start_date")
    date_hierarchy = "start_date"
    raw_id_fields = ("personnel",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "duration_calculation",
        "remaining_allowance",
    )
    actions = ["export_as_csv", "approve_leaves", "reject_leaves"]

    fieldsets = (
        (
            "Demande de congé",
            {"fields": ("personnel", "leave_type", "start_date", "end_date", "reason")},
        ),
        ("Calculs", {"fields": ("duration_calculation", "remaining_allowance")}),
        ("Statut", {"fields": ("status",)}),
        (
            "Métadonnées",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def personnel_link(self, obj):
        url = reverse("admin:rh_personnel_change", args=[obj.personnel.id])
        return format_html('<a href="{}">{}</a>', url, obj.personnel.nom_prenom)

    personnel_link.short_description = "Employé"
    personnel_link.admin_order_field = "personnel__nom_prenom"

    def duration_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return "-"

    duration_days.short_description = "Durée (jours)"

    def colored_status(self, obj):
        colors = {
            "PENDING": ("orange", "⏳"),
            "APPROVED": ("green", "✓"),
            "REJECTED": ("red", "✗"),
        }
        color, icon = colors.get(obj.status, ("black", "?"))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_status_display(),
        )

    colored_status.short_description = "Statut"
    colored_status.admin_order_field = "status"

    def urgency_indicator(self, obj):
        """Indicateur d'urgence basé sur la proximité de la date"""
        if obj.start_date and obj.status == "PENDING":
            days_until = (obj.start_date - timezone.now().date()).days
            if days_until < 0:
                return format_html(
                    '<span style="color: red; font-weight: bold;">URGENT - Déjà commencé!</span>'
                )
            elif days_until <= 7:
                return format_html(
                    '<span style="color: orange; font-weight: bold;">Urgent - Dans {} jours</span>',
                    days_until,
                )
            elif days_until <= 30:
                return format_html(
                    '<span style="color: blue;">Dans {} jours</span>', days_until
                )
        return "-"

    urgency_indicator.short_description = "Urgence"

    def duration_calculation(self, obj):
        if obj.start_date and obj.end_date:
            days = (obj.end_date - obj.start_date).days + 1
            return f"{days} jours"
        return "Non calculé"

    duration_calculation.short_description = "Durée calculée"

    def remaining_allowance(self, obj):
        """Calcul des congés restants pour ce type"""
        if obj.personnel and obj.leave_type:
            remaining = obj.personnel.get_remaining_leave_days(obj.leave_type)
            return f"{remaining} jours restants"
        return "Non calculé"

    remaining_allowance.short_description = "Solde congés"

    def approve_leaves(self, request, queryset):
        updated = queryset.filter(status="PENDING").update(status="APPROVED")
        self.message_user(request, f"{updated} demande(s) de congé approuvée(s).")

    approve_leaves.short_description = "Approuver les congés"

    def reject_leaves(self, request, queryset):
        updated = queryset.filter(status="PENDING").update(status="REJECTED")
        self.message_user(request, f"{updated} demande(s) de congé rejetée(s).")

    reject_leaves.short_description = "Rejeter les congés"


# ─── Configuration globale de l'admin ────────────────────────────────────────
admin.site.site_header = "Administration RH - Système de Gestion"
admin.site.site_title = "Admin RH"
admin.site.index_title = "Tableau de bord RH"
