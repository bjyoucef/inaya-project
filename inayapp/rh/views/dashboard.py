import logging
from datetime import date, datetime

from accueil.models import ConfigDate
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import (
    LeaveRequest,
    Personnel,
    SalaryAdvanceRequest,
)
from .utils import get_date_range

logger = logging.getLogger(__name__)


@login_required
def salary_advance_create(request):
    """
    Traite la demande d'avance sur salaire.
    """
    if request.method == "POST":
        personnel = request.user.personnel
        amount = request.POST.get("amount")
        payment_date = request.POST.get("payment_date")
        reason = request.POST.get("reason")

        # Crée la demande d'avance sur salaire
        SalaryAdvanceRequest.objects.create(
            personnel=personnel,
            amount=amount,
            payment_date=payment_date,
            reason=reason,
            request_date=timezone.now(),  # facultatif si le default de request_date est bien défini
        )
        # Redirige vers le dashboard après soumission
        return redirect("dashboard")
    return redirect("dashboard")


@login_required
def leave_request_create(request):
    """
    Traite la demande de congé.
    """
    if request.method == "POST":
        personnel = request.user.personnel
        leave_type = request.POST.get("leave_type")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        reason = request.POST.get("reason")

        # Crée la demande de congé
        LeaveRequest.objects.create(
            personnel=personnel,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )
        # Redirige vers le dashboard après soumission
        return redirect("dashboard")
    return redirect("dashboard")


@login_required
def dashboard(request):
    user = request.user
    can_treat = user.has_perm("rh.process_salaryadvance_request") or user.has_perm(
        "rh.process_leave_request"
    )

    # Récupération du paramètre employé depuis la requête GET
    employee_id = request.GET.get("employee")
    status_filter = request.GET.get("status", "")  # Récupère le statut sélectionné

    # Récupération ou création de la configuration liée à l'utilisateur pour la page "dashboard_rh"
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="dashboard_rh",
        defaults={"start_date": date.today(), "end_date": date.today()},
    )

    # Mise à jour des dates si elles sont passées en GET
    for param in ["start_date", "end_date"]:
        value = request.GET.get(param)
        if value:
            try:
                parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
                setattr(config, param, parsed_date)
            except ValueError:
                pass  # Vous pouvez logguer l'erreur ici si nécessaire
    config.save()

    # Obtention d'une plage de dates correcte
    start_date, end_date = get_date_range(config)

    # Récupération uniquement des employés ayant au moins une demande (avance ou congé)
    personnels = Personnel.objects.filter(
        Q(salary_advances__isnull=False) | Q(leave_requests__isnull=False)
    ).distinct()

    if can_treat:
        filter_kwargs = {}
        if employee_id:
            filter_kwargs["personnel_id"] = employee_id

        salary_requests = SalaryAdvanceRequest.objects.filter(
            **filter_kwargs,
            request_date__gte=start_date,
            request_date__lte=end_date,
        ).order_by("-created_at")
        leave_requests = LeaveRequest.objects.filter(
            **filter_kwargs,
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).order_by("-created_at")

        # Application du filtre sur le statut si renseigné
        if status_filter:
            salary_requests = salary_requests.filter(status=status_filter)
            leave_requests = leave_requests.filter(status=status_filter)

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
        leave_requests = LeaveRequest.objects.filter(personnel=user.personnel).order_by(
            "-created_at"
        )

        if status_filter:
            salary_requests = salary_requests.filter(status=status_filter)
            leave_requests = leave_requests.filter(status=status_filter)

        pending_salary = salary_requests.filter(
            status=SalaryAdvanceRequest.RequestStatus.PENDING
        ).count()
        pending_leave = leave_requests.filter(
            status=LeaveRequest.RequestStatus.PENDING
        ).count()

    context = {
        "salary_requests": salary_requests,
        "leave_requests": leave_requests,
        "can_treat": can_treat,
        "pending_count": pending_salary + pending_leave,
        "personnels": personnels,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "selected_employee": employee_id,
        "selected_status": status_filter,  # Pour pré-sélectionner l'option dans le template
    }
    return render(request, "rh/dashboard.html", context)


@permission_required("rh.process_salaryadvance_request", raise_exception=True)
@login_required
def process_salary_request(request, request_id, action):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    salary_request = get_object_or_404(SalaryAdvanceRequest, id=request_id)

    # Validation de l'action
    if action not in ["approve", "reject", "cancel"]:
        return HttpResponseBadRequest("Action invalide")

    # Logique de traitement
    if action == "approve":
        salary_request.status = SalaryAdvanceRequest.RequestStatus.APPROVED
    elif action == "reject":
        salary_request.status = SalaryAdvanceRequest.RequestStatus.REJECTED
    elif action == "cancel":
        salary_request.status = SalaryAdvanceRequest.RequestStatus.CANCELED

    salary_request.save()

    return redirect("dashboard")


@permission_required("rh.process_leave_request", raise_exception=True)
@login_required
def process_leave_request(request, request_id, action):
    """
    Permet de traiter une demande de congé.
    L'action peut être 'approve', 'reject' ou 'cancel'.
    Seuls les utilisateurs disposant de la permission 'rh.process_leave_request'
    peuvent accéder à cette vue.
    """
    leave_request = get_object_or_404(LeaveRequest, id=request_id)

    if action == "approve":
        leave_request.status = LeaveRequest.RequestStatus.APPROVED
    elif action == "reject":
        leave_request.status = LeaveRequest.RequestStatus.REJECTED
    elif action == "cancel":
        leave_request.status = LeaveRequest.RequestStatus.CANCELED
    leave_request.save()

    return redirect("dashboard")
