# accueil/context_processors.py


from django.db import models
from django.db.models import ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import Resolver404, resolve, reverse
from finance.models import Decharges
from helpdesk.models import Helpdesk
from rh.models import LeaveRequest, SalaryAdvanceRequest
from django.urls import resolve, reverse

from .models import MenuItem, NavbarItem

from .models import MenuGroup, MenuItem, NavbarItem


def get_menu_groups(request):
    groups = MenuGroup.objects.prefetch_related("items").all()
    return {"menu_groups": groups}


def get_menu_items(request):
    items = MenuItem.objects.all().order_by("order")
    filtered_items = []

    for item in items:
        if item.permission:
            if request.user.is_authenticated and request.user.has_perm(item.permission):
                filtered_items.append(item)
        else:
            filtered_items.append(item)

    return {"menu_items": filtered_items}


def navbar_context(request):
    # 1) obtenir le nom de la vue courante
    try:
        current_url_name = resolve(request.path_info).route
    except Exception:
        current_url_name = None

    # 2) MenuItem actif
    active_item = (
        MenuItem.objects.filter(route=f"/{current_url_name}").first()
        if current_url_name
        else None
    )

    # 3) charger tous les NavbarItem et permissions
    if active_item:
        qs = (
            NavbarItem.objects.filter(menu_item=active_item)
            .select_related("menu_item")
            .order_by("order")
        )
    else:
        qs = NavbarItem.objects.none()

    user_perms = request.user.get_all_permissions() if request.user.is_authenticated else set()
    
    # 4) Filtrer par permissions
    user_perms = (
        request.user.get_all_permissions() if request.user.is_authenticated else set()
    )
    navbar_items = [
        nb
        for nb in qs
        if (not nb.permission or nb.permission in user_perms)
        and (not active_item.permission or active_item.permission in user_perms)
    ]

    return {
        "navbar_items": navbar_items,
        "active_menu_item": active_item,
        "current_url_name": current_url_name,
    }


def notification(request):
    user = request.user

    nembre_notification_hd = 0
    pending_salary = 0
    pending_leave = 0
    pending_decharges = 0
    
    if user.is_authenticated:
        id_personnel = user.id

        # Conditions Helpdesk
        condition = Q(name=id_personnel) & Q(time_terminee__isnull=True)

        if user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_IT"):
            condition |= Q(type="it") & Q(time_terminee__isnull=True)
        if user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE"):
            condition |= Q(type="tech") & Q(time_terminee__isnull=True)
        if user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT"):
            condition |= Q(type="appro") & Q(time_terminee__isnull=True)

        demandes = Helpdesk.objects.filter(condition)
        nembre_notification_hd = demandes.count()

        # RH - Gestion des demandes
        if user.has_perm("rh.process_salaryadvance_request") or user.has_perm(
            "rh.process_leave_request"
        ):
            pending_salary = SalaryAdvanceRequest.objects.filter(
                status=SalaryAdvanceRequest.RequestStatus.PENDING
            ).count()
            pending_leave = LeaveRequest.objects.filter(
                status=LeaveRequest.RequestStatus.PENDING
            ).count()
        else:
            if hasattr(user, "personnel"):
                salary_requests = SalaryAdvanceRequest.objects.filter(
                    personnel=user.personnel
                ).order_by("-created_at")

                leave_requests = LeaveRequest.objects.filter(
                    personnel=user.personnel
                ).order_by("-created_at")

                pending_salary = salary_requests.filter(
                    status=SalaryAdvanceRequest.RequestStatus.PENDING
                ).count()

                pending_leave = leave_requests.filter(
                    status=LeaveRequest.RequestStatus.PENDING
                ).count()

        # finance - Gestion des decharges
        if user.has_perm("finance.process_expense_request"):
            pending_decharges = (
                Decharges.objects.annotate(
                    total_payments=Coalesce(
                        Sum("payments__payment"),
                        Value(0, output_field=models.DecimalField()),
                        output_field=models.DecimalField(),
                    )
                )
                .annotate(
                    balance=ExpressionWrapper(
                        F("amount") - F("total_payments"),
                        output_field=models.DecimalField(
                            max_digits=10, decimal_places=2
                        ),
                    )
                )
                .filter(balance__gt=0)
            ).count()
        else:
            pending_decharges = ''

    return {
        "nembre_notification_hd": nembre_notification_hd,
        "nembre_notification_rh": pending_salary + pending_leave,
        "nembre_notification_decharge": pending_decharges,
    }
