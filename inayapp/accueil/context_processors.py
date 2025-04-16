# accueil/context_processors.py

from rh.models import LeaveRequest, SalaryAdvanceRequest
from .models import MenuItems
from helpdesk.models import Helpdesk
from django.db.models import Q


def menu_items(request):
    items = MenuItems.objects.all().order_by("n")
    filtered_items = []

    for item in items:
        if item.permission:
            if request.user.is_authenticated and request.user.has_perm(item.permission):
                filtered_items.append(item)
        else:
            filtered_items.append(item)

    return {"menu_items": filtered_items}


def notification(request):
    user = request.user

    nembre_notification_hd = 0
    pending_salary = 0
    pending_leave = 0

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

    return {
        "nembre_notification_hd": nembre_notification_hd,
        "nembre_notification_rh": pending_salary + pending_leave,
    }
