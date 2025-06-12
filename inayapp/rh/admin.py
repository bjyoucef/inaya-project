from django.contrib import admin
from .models import (
    Personnel,
    Employee,
    Planning,
    Pointage,
    SalaryAdvanceRequest,
    LeaveRequest,
    Poste,
    GlobalSalaryConfig,
    IRGBracket,
    HonorairesActe,
    PointagesActes,
    ShiftType,
)


# ─── Employee ────────────────────────────────────────────────────────────────
class PersonnelInline(admin.StackedInline):
    model = Personnel
    fk_name = "employee"
    max_num = 1
    can_delete = False
    fields = ("nom_prenom", "poste", "service", "telephone", "salaire")
    readonly_fields = ("created_at", "updated_at")


# in admin.py


# admin.py

from django.utils import timezone
from datetime import timedelta


class PointageInline(admin.TabularInline):
    model = Pointage
    extra = 0
    readonly_fields = ("check_time", "synced_at")
    fields = ("check_time",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # show only pointages from the last 30 days
        cutoff = timezone.now() - timedelta(days=1)
        return qs.filter(check_time__gte=cutoff).order_by("-check_time")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "anviz_id",
        "shift_type",
        "last_updated",
    )
    search_fields = ("name", "anviz_id")
    list_filter = ("shift_type",)
    date_hierarchy = "last_updated"
    ordering = ("-last_updated",)
    inlines = [PersonnelInline, PointageInline]
    autocomplete_fields = ("shift_type",)
    readonly_fields = ("last_updated",)


# ─── Personnel ───────────────────────────────────────────────────────────────
class PlanningInline(admin.TabularInline):
    model = Planning
    fk_name = "employee"
    extra = 0
    fields = ("shift_date", "shift", "service", "prix", "paiement")
    raw_id_fields = ("service", "shift")
    date_hierarchy = "shift_date"


class SalaryAdvanceRequestInline(admin.TabularInline):
    model = SalaryAdvanceRequest
    extra = 0
    fields = ("amount", "request_date", "payment_date", "status", "reason")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "request_date"


class LeaveRequestInline(admin.TabularInline):
    model = LeaveRequest
    extra = 0
    fields = ("start_date", "end_date", "leave_type", "status", "reason")
    date_hierarchy = "start_date"


@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = (
        "nom_prenom",
        "poste",
        "service",
        "telephone",
        "salaire",
        "statut_activite",
    )
    search_fields = ("nom_prenom", "telephone")
    list_filter = ("poste", "service", "statut_activite", "use_in_planning")
    date_hierarchy = "created_at"
    ordering = ("nom_prenom",)
    inlines = [PlanningInline, SalaryAdvanceRequestInline, LeaveRequestInline]
    raw_id_fields = ("user", "employee")
    readonly_fields = ("created_at", "updated_at")


# ─── Planning ────────────────────────────────────────────────────────────────
class PointagesActesInline(admin.TabularInline):
    model = PointagesActes
    extra = 1
    fields = ("id_acte", "nbr_actes")
    raw_id_fields = ("id_acte",)


@admin.register(Planning)
class PlanningAdmin(admin.ModelAdmin):
    list_display = ("shift_date", "employee", "shift", "service", "paiement")
    search_fields = ("employee__nom_prenom", "service__name")
    list_filter = ("shift", "service")
    date_hierarchy = "shift_date"
    inlines = [PointagesActesInline]
    raw_id_fields = ("employee", "service", "shift", "id_created_par")


# ─── Poste & HonorairesActe ─────────────────────────────────────────────────
class HonorairesActeInline(admin.TabularInline):
    model = HonorairesActe
    extra = 1
    fields = ("name_acte", "prix_acte")


@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    list_display = ("label",)
    search_fields = ("label",)
    inlines = [HonorairesActeInline]


# ─── GlobalSalaryConfig & IRGBracket ────────────────────────────────────────
class IRGBracketInline(admin.TabularInline):
    model = IRGBracket
    extra = 1
    fields = ("min_amount", "max_amount", "tax_rate")


@admin.register(GlobalSalaryConfig)
class GlobalSalaryConfigAdmin(admin.ModelAdmin):
    list_display = (
        "update_date",
        "updated_by",
        "cnas_employer_rate",
        "cnas_employee_rate",
    )
    list_filter = ("updated_by",)
    date_hierarchy = "update_date"
    inlines = [IRGBracketInline]
    readonly_fields = ("update_date",)


# ─── SalaryAdvanceRequest & LeaveRequest ────────────────────────────────────
@admin.register(SalaryAdvanceRequest)
class SalaryAdvanceRequestAdmin(admin.ModelAdmin):
    list_display = ("personnel", "amount", "request_date", "payment_date", "status")
    search_fields = ("personnel__nom_prenom",)
    list_filter = ("status",)
    date_hierarchy = "request_date"
    raw_id_fields = ("personnel",)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("personnel", "leave_type", "start_date", "end_date", "status")
    search_fields = ("personnel__nom_prenom",)
    list_filter = ("leave_type", "status")
    date_hierarchy = "start_date"
    raw_id_fields = ("personnel",)


@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    search_fields = ("name",)
