# accueil/context_processors.py
from rh.models import LeaveRequest, SalaryAdvanceRequest
from .models import MenuItems
from helpdesk.models import Helpdesk
from django.db.models import Q


def menu_items(request):
    # Récupération de tous les éléments de menu triés
    items = MenuItems.objects.all().order_by("n")
    # Liste qui contiendra les éléments filtrés
    filtered_items = []

    for item in items:
        if item.permission:
            # Si une permission est définie, on vérifie que l'utilisateur la possède
            if request.user.has_perm(item.permission):
                filtered_items.append(item)
        else:
            # Si aucune permission n'est définie, on affiche l'élément par défaut
            filtered_items.append(item)

    return {"menu_items": filtered_items}


from helpdesk.models import Helpdesk
from django.db.models import Q


def notification(request):
    user = request.user
    id_personnel = user.id

    # On définit une condition pour les demandes non terminées (time_terminee est NULL)
    # et qui appartiennent à l'utilisateur (name == id_personnel)
    condition = Q(name=id_personnel) & Q(time_terminee__isnull=True)

    # Si l'utilisateur a la permission d'accéder au département IT, on ajoute aussi les demandes de type 'it'
    if request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_IT"):
        condition |= Q(type="it") & Q(time_terminee__isnull=True)
    # Pour le département technique
    if request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE"):
        condition |= Q(type="tech") & Q(time_terminee__isnull=True)
    # Pour le département approvisionnement
    if request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT"):
        condition |= Q(type="appro") & Q(time_terminee__isnull=True)

    demandes = Helpdesk.objects.filter(condition)
    nembre_notification_hd = demandes.count()

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
        salary_requests = SalaryAdvanceRequest.objects.filter(
            personnel=user.personnel
        ).order_by("-created_at")
        leave_requests = LeaveRequest.objects.filter(
            personnel=user.personnel
            ).order_by(
            "-created_at"
        )
            
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
