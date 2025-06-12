from decimal import Decimal
import logging
from datetime import date, datetime

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum
# Assurez-vous d'avoir ces imports
from django.http import (HttpResponseBadRequest, HttpResponseNotAllowed,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from finance.models import Decharges, Payments
from utils.utils import get_date_range

from ..models import LeaveRequest, Personnel, SalaryAdvanceRequest

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def salary_advance_create(request):
    """Créer une demande d'avance sur salaire avec validation"""
    try:
        if request.user.has_perm('personnel.create_for_others'):
            personnel_id = request.POST.get("personnel_id")
            if personnel_id:
                personnel = get_object_or_404(Personnel, id_personnel=personnel_id)
            else:
                personnel = request.user.personnel
        else:
            personnel = request.user.personnel

        # Vérifier s'il y a déjà une demande en attente pour ce personnel
        pending_request = SalaryAdvanceRequest.objects.filter(
            personnel=personnel, status=SalaryAdvanceRequest.RequestStatus.PENDING
        ).exists()

        if pending_request:
            messages.error(
                request,
                "Une demande d'avance est déjà en attente pour cet employé. "
                "Veuillez traiter la demande existante avant d'en créer une nouvelle.",
            )
            return redirect("demandes")
        
        
        amount = Decimal(request.POST.get("amount", "0"))
        payment_date_str = request.POST.get("payment_date")
        reason = request.POST.get("reason", "").strip()

        # Validation des données
        if not amount or amount <= 0:
            messages.error(request, "Le montant doit être positif")
            return redirect("demandes")

        if not payment_date_str:
            messages.error(request, "La date de paiement est requise")
            return redirect("demandes")

        try:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Format de date invalide")
            return redirect("demandes")

        if not reason:
            messages.error(request, "Le motif est requis")
            return redirect("demandes")

        # Vérifier le montant disponible
        available_amount = personnel.get_available_advance_amount()
        if amount > available_amount:
            messages.error(
                request,
                f"Montant demandé ({amount}) supérieur au montant disponible ({available_amount})",
            )
            return redirect("demandes")

        # Créer la demande
        advance_request = SalaryAdvanceRequest(
            personnel=personnel, amount=amount, payment_date=payment_date, reason=reason
        )
        advance_request.full_clean()  # Validation complète
        advance_request.save()

        messages.success(request, "Demande d'avance soumise avec succès")
        logger.info(
            f"Nouvelle demande d'avance créée par {personnel.nom_prenom} - Montant: {amount}"
        )

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la création de la demande d'avance: {e}")
        messages.error(request, "Une erreur est survenue lors de la soumission")

    return redirect("demandes")


@login_required
@require_http_methods(["POST"])
def leave_request_create(request):
    """Créer une demande de congé avec validation"""
    try:
        if request.user.has_perm('personnel.create_for_others'):
            personnel_id = request.POST.get("personnel_id")
            if personnel_id:
                personnel = get_object_or_404(Personnel, id_personnel=personnel_id)
            else:
                personnel = request.user.personnel
        else:
            personnel = request.user.personnel

        # Vérifier s'il y a déjà une demande en attente pour ce personnel
        pending_request = LeaveRequest.objects.filter(
            personnel=personnel, status=LeaveRequest.RequestStatus.PENDING
        ).exists()

        if pending_request:
            messages.error(
                request,
                "Une demande de congé est déjà en attente pour cet employé. "
                "Veuillez traiter la demande existante avant d'en créer une nouvelle.",
            )
            return redirect("demandes")
        
        
        leave_type = request.POST.get("leave_type")
        start_date_str = request.POST.get("start_date")
        end_date_str = request.POST.get("end_date")
        reason = request.POST.get("reason", "").strip()

        # Validation des données
        if not all([leave_type, start_date_str, end_date_str, reason]):
            messages.error(request, "Tous les champs sont requis")
            return redirect("demandes")

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Format de date invalide")
            return redirect("demandes")

        # Créer la demande
        leave_request = LeaveRequest(
            personnel=personnel,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )
        leave_request.full_clean()  # Validation complète
        leave_request.save()

        messages.success(request, "Demande de congé soumise avec succès")
        logger.info(
            f"Nouvelle demande de congé créée par {personnel.nom_prenom} - Du {start_date} au {end_date}"
        )

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la création de la demande de congé: {e}")
        messages.error(request, "Une erreur est survenue lors de la soumission")

    return redirect("demandes")


@login_required
def demandes(request):
    # Récupération des paramètres de filtrage
    filters = {
        "search": request.GET.get("search", ""),
        "statut": request.GET.get("statut", ""),
        "personnel": request.GET.get("personnel", ""),
        # Utiliser les champs cachés pour les dates
        "start_date": request.GET.get("start_date", ""),
        "end_date": request.GET.get("end_date", ""),
    }
    # Récupération ou création de la configuration liée à l'utilisateur pour la page "dashboard_rh"
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="dashboard_rh",
        defaults={"start_date": date.today(), "end_date": date.today()},
    )

    # Mise à jour des dates si fournies dans les filtres
    if filters["start_date"]:
        try:
            config.start_date = datetime.strptime(
                filters["start_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            pass

    if filters["end_date"]:
        try:
            config.end_date = datetime.strptime(filters["end_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    config.save()

    # Obtention d'une plage de dates correcte
    start_date, end_date = get_date_range(config)

    # Construction des querysets avec filtres
    salary_requests = SalaryAdvanceRequest.objects.filter(
        request_date__range=[start_date, end_date]
    ).order_by("-created_at")

    leave_requests = LeaveRequest.objects.filter(
        created_at__range=[start_date, end_date]
    ).order_by("-created_at")

    # Application des filtres supplémentaires
    if filters["search"]:
        search_term = filters["search"]
        salary_requests = salary_requests.filter(
            Q(id__icontains=search_term)
            | Q(personnel__nom_prenom__icontains=search_term)
            | Q(reason__icontains=search_term)
        )
        leave_requests = leave_requests.filter(
            Q(id__icontains=search_term)
            | Q(personnel__nom_prenom__icontains=search_term)
            | Q(reason__icontains=search_term)
        )

    if filters["statut"]:
        salary_requests = salary_requests.filter(status=filters["statut"])
        leave_requests = leave_requests.filter(status=filters["statut"])

    if filters["personnel"]:
        salary_requests = salary_requests.filter(personnel_id=filters["personnel"])
        leave_requests = leave_requests.filter(personnel_id=filters["personnel"])

    # Récupération des données pour les listes déroulantes
    all_personnels = Personnel.objects.filter(salary_advance_request=True).exclude(
        salaire=0
    )
    statuts = (
        SalaryAdvanceRequest.RequestStatus.choices
    )  # Ou LeaveRequest.RequestStatus.choices

    context = {
        "salary_requests": salary_requests,
        "leave_requests": leave_requests,
        "all_personnels": all_personnels,
        "statuts": statuts,
        "filters": {
            "search": filters["search"],
            "statut": filters["statut"],
            "personnel": filters["personnel"],
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
    }
    return render(request, "dashboard_rh.html", context)


@login_required
@require_http_methods(["POST"])
def process_salary_request(request, request_id, action):
    """Traiter une demande d'avance sur salaire"""
    try:
        salary_request = get_object_or_404(SalaryAdvanceRequest, id=request_id)

        # Vérifier si la demande peut être traitée
        if not salary_request.can_be_processed():
            messages.error(request, "Cette demande ne peut plus être traitée")
            return redirect("demandes")

        # Validation de l'action
        if action not in ["approve", "reject", "cancel"]:
            return HttpResponseBadRequest("Action invalide")

        rejection_reason = request.POST.get("rejection_reason", "").strip()

        # Traitement selon l'action
        if action == "approve":
            salary_request.status = SalaryAdvanceRequest.RequestStatus.APPROVED

            # Création automatique de la décharge
            from finance.models import Decharges

            decharge = Decharges.objects.create(
                name=f"Avance sur salaire - {salary_request.personnel.nom_prenom}",
                amount=salary_request.amount,
                date=salary_request.payment_date,
                note=f"Décharge créée automatiquement pour la demande d'avance #{salary_request.id}\nMotif: {salary_request.reason}",
                created_at=timezone.now(),
                id_created_par=request.user,
                id_employe=salary_request.personnel.id_personnel,
            )

            messages.success(
                request,
                f"Demande approuvée et décharge #{decharge.id_decharge} créée automatiquement",
            )
            logger.info(
                f"Demande d'avance #{salary_request.id} approuvée par {request.user.username}"
            )

        elif action == "reject":
            if not rejection_reason:
                messages.error(request, "Le motif de rejet est requis")
                return redirect("demandes")

            salary_request.status = SalaryAdvanceRequest.RequestStatus.REJECTED
            salary_request.rejection_reason = rejection_reason
            messages.success(request, "Demande rejetée avec succès")
            logger.info(
                f"Demande d'avance #{salary_request.id} rejetée par {request.user.username}"
            )

        elif action == "cancel":
            salary_request.status = SalaryAdvanceRequest.RequestStatus.CANCELED
            messages.success(request, "Demande annulée avec succès")
            logger.info(
                f"Demande d'avance #{salary_request.id} annulée par {request.user.username}"
            )

        # Mettre à jour les informations de traitement
        salary_request.processed_by = request.user
        salary_request.processed_at = timezone.now()
        salary_request.save()

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la demande d'avance: {e}")
        messages.error(request, "Une erreur est survenue lors du traitement")

    return redirect("demandes")


@login_required
@require_http_methods(["POST"])
def process_leave_request(request, request_id, action):
    """Traiter une demande de congé"""
    try:
        leave_request = get_object_or_404(LeaveRequest, id=request_id)

        # Vérifier si la demande peut être traitée
        if not leave_request.can_be_processed():
            messages.error(request, "Cette demande ne peut plus être traitée")
            return redirect("demandes")

        # Validation de l'action
        if action not in ["approve", "reject", "cancel"]:
            return HttpResponseBadRequest("Action invalide")

        rejection_reason = request.POST.get("rejection_reason", "").strip()

        # Traitement selon l'action
        if action == "approve":
            leave_request.status = LeaveRequest.RequestStatus.APPROVED
            messages.success(request, "Demande de congé approuvée avec succès")
            logger.info(
                f"Demande de congé #{leave_request.id} approuvée par {request.user.username}"
            )

        elif action == "reject":
            if not rejection_reason:
                messages.error(request, "Le motif de rejet est requis")
                return redirect("demandes")

            leave_request.status = LeaveRequest.RequestStatus.REJECTED
            leave_request.rejection_reason = rejection_reason
            messages.success(request, "Demande de congé rejetée avec succès")
            logger.info(
                f"Demande de congé #{leave_request.id} rejetée par {request.user.username}"
            )

        elif action == "cancel":
            leave_request.status = LeaveRequest.RequestStatus.CANCELED
            messages.success(request, "Demande de congé annulée avec succès")
            logger.info(
                f"Demande de congé #{leave_request.id} annulée par {request.user.username}"
            )

        # Mettre à jour les informations de traitement
        leave_request.processed_by = request.user
        leave_request.processed_at = timezone.now()
        leave_request.save()

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la demande de congé: {e}")
        messages.error(request, "Une erreur est survenue lors du traitement")

    return redirect("demandes")


@login_required
def get_available_advance_amount(request):
    try:
        personnel_id = request.GET.get("personnel_id")
        if personnel_id and request.user.has_perm('personnel.create_for_others'):
            personnel = get_object_or_404(Personnel, id_personnel=personnel_id)
        else:
            personnel = request.user.personnel
        
        available_amount = personnel.get_available_advance_amount()
        return JsonResponse(
            {"available_amount": str(available_amount), "max_salary_percentage": 30}
        )
    except Exception as e:
        logger.error(f"Error fetching available amount: {e}")
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def get_remaining_leave_days(request):
    try:
        personnel_id = request.GET.get("personnel_id")
        leave_type = request.GET.get("leave_type")

        if not leave_type:
            return JsonResponse({"error": "Leave type required"}, status=400)

        if personnel_id and request.user.has_perm("personnel.create_for_others"):
            personnel = get_object_or_404(Personnel, id_personnel=personnel_id)
        else:
            personnel = request.user.personnel

        remaining_days = personnel.get_remaining_leave_days(leave_type)
        return JsonResponse(
            {"remaining_days": remaining_days, "leave_type": leave_type}
        )
    except Exception as e:
        logger.error(f"Error fetching remaining leave days: {e}")
        return JsonResponse({"error": str(e)}, status=400)
