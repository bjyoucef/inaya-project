import json
import logging
from datetime import date, datetime, timedelta
from io import BytesIO

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
from xhtml2pdf import pisa
from collections import defaultdict
from decimal import Decimal
from ..models import (HonorairesActe, Personnel, Planning, PointagesActes,
                      Services)

logger = logging.getLogger(__name__)


def extract_filters(request):
    """
    Extrait les filtres de la requête et retourne un dictionnaire avec des valeurs par défaut.
    """
    return {
        "service": request.GET.get("service", "all"),
        "employee": request.GET.get("employee", "all"),
        "shift": request.GET.get("shift", "all"),
        "start_date": request.GET.get("start_date", ""),
        "end_date": request.GET.get("end_date", ""),
    }


def build_redirect_params(filters):
    """
    Construit les paramètres de redirection à partir des filtres.
    """
    return (
        f"?service={filters['service']}&shift={filters['shift']}"
        f"&employee={filters['employee']}&start_date={filters['start_date']}"
        f"&end_date={filters['end_date']}"
    )


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def planning(request):
    # Extraction et configuration des filtres
    filters = extract_filters(request)
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="planning",
        defaults={"start_date": "2025-01-01", "end_date": "2025-01-01"},
    )
    if filters.get("start_date"):
        config.start_date = filters["start_date"]
    if filters.get("end_date"):
        config.end_date = filters["end_date"]
    config.save()

    # Utiliser les dates des filtres ou celles du config
    start_date = filters.get("start_date") or config.start_date
    end_date = filters.get("end_date") or config.end_date

    # Convertir en ISO pour la comparaison (si nécessaire)
    filters["start_date"] = (
        start_date.isoformat() if isinstance(start_date, date) else start_date
    )
    filters["end_date"] = (
        end_date.isoformat() if isinstance(end_date, date) else end_date
    )

    # Construction du filtre de requête pour Planning
    planning_filter = Q(shift_date__range=[filters["start_date"], filters["end_date"]])
    pointage_filter = Q(
        id_planning__shift_date__range=[filters["start_date"], filters["end_date"]]
    )

    if filters.get("service", "all") != "all":
        planning_filter &= Q(id_service__service_name=filters["service"])
        pointage_filter &= Q(id_planning__id_service__service_name=filters["service"])

    if filters.get("employee", "all") != "all":
        employee_name = filters["employee"].strip()
        planning_filter &= Q(employee__nom_prenom__icontains=employee_name)
        pointage_filter &= Q(id_planning__employee__nom_prenom__icontains=employee_name)

    if filters.get("shift", "all") != "all":
        planning_filter &= Q(shift_type=filters["shift"])
        pointage_filter &= Q(id_planning__shift_type=filters["shift"])

    try:
        planningsValidees = Planning.objects.select_related("employee", "id_service").filter(
            planning_filter, pointage_created_at__isnull=False
        )

        # Récupération des plannings avec jointures optimisées
        plannings = Planning.objects.select_related("employee", "id_service").filter(planning_filter)

        # Récupération des pointages d'actes avec jointures optimisées et tri par date
        pointages = PointagesActes.objects.select_related(
            "id_planning__employee", "id_planning__id_service", "id_acte"
        ).filter(pointage_filter).order_by("id_planning__shift_date")

    except Exception:
        logger.exception("Erreur lors du filtrage des plannings")
        plannings = Planning.objects.none()
        planningsValidees = Planning.objects.none()
        pointages = PointagesActes.objects.none()

    # Récupération des services autorisés et des employés actifs
    services = [
        s
        for s in Services.objects.all()
        if request.user.has_perm(f"rh.view_service_{s.service_name}")
    ]
    employees = Personnel.objects.filter(statut_activite=1, use_in_planning=1).order_by(
        "nom_prenom"
    )

    # Préparation des couleurs de services et configuration des shifts
    service_colors = {s.service_name: s.color for s in services}
    shift_configs = {
        "jour": (timedelta(hours=8), timedelta(hours=8)),
        "nuit": (timedelta(hours=17), timedelta(hours=16)),
        "24H": (timedelta(hours=8), timedelta(hours=24)),
    }

    # Construction de la liste des événements pour FullCalendar
    events = []
    for p in plannings.iterator():
        time_config = shift_configs.get(p.shift_type)
        if time_config and all(time_config):
            event_start = (
                datetime.combine(p.shift_date, datetime.min.time()) + time_config[0]
            )
            event_end = event_start + time_config[1]
            events.append(
                {
                    "id": p.id,
                    "service_id": p.id_service.id_service,
                    "title": f"{p.employee} - {p.shift_type} - {p.id_service.service_name}",
                    "start": event_start.isoformat(),
                    "end": event_end.isoformat(),
                    "backgroundColor": (
                        "gray"
                        if p.pointage_created_at
                        else service_colors.get(p.id_service.service_name, "black")
                    ),
                    "borderColor": service_colors.get(
                        p.id_service.service_name, "black"
                    ),
                }
            )

    # Calculer le total (prix unitaire * nombre d'actes) pour chaque pointage
    for pa in pointages:
        pa.total = pa.id_acte.prix_acte * pa.nbr_actes
    # Dictionnaire pour grouper par employé
    grouped_plannings = defaultdict(lambda: {
        "employee": None,
        "prix_total": Decimal(0),
        "prix_acte_total": Decimal(0),
        "pointagesDetail": []
    })
    # Grouper
    for planning in planningsValidees:
        emp_id = planning.employee.id_personnel
        grouped_plannings[emp_id]["employee"] = planning.employee
        grouped_plannings[emp_id]["prix_total"] += planning.prix or 0
        grouped_plannings[emp_id]["prix_acte_total"] += planning.prix_acte or 0

        grouped_plannings[emp_id]["pointagesDetail"].append({
            "service_name": planning.id_service.service_name,
            "date_pointage": planning.shift_date.strftime("%Y-%m-%d"),
            "shift_type": planning.shift_type,
            "prix": planning.prix,
            "prix_acte": planning.prix_acte,
        })

    # Transformer en liste pour le template
    plannings_groupes = list(grouped_plannings.values())

    context = {
        "planningsValidees": plannings_groupes,
        "employees": employees,
        "services": services,
        "events": events,
        "selected": filters,
        "title": "Plannings",
        "user": request.user,
        "pointages": pointages,
    }
    return render(request, "rh/planning.html", context)


@permission_required("rh.creer_planning", raise_exception=True)
def save_planning(request):
    # Extraction centralisée des filtres (GET ou POST)
    filters = (
        {
            "service": request.POST.get("service", "all"),
            "employee": request.POST.get("employee", "all"),
            "shift": request.POST.get("shift", "all"),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
        }
        if request.method == "POST"
        else extract_filters(request)
    )

    redirect_params = build_redirect_params(filters)
    if request.method != "POST":
        return redirect(reverse("planning") + redirect_params)

    # Récupération et validation des données du formulaire
    service_name = request.POST.get("service")
    employee_full_name = request.POST.get("employee")
    shift_type = request.POST.get("shift")
    shift_date_str = request.POST.get("date")
    event_id = request.POST.get("event_id")

    if not all([service_name, employee_full_name, shift_type, shift_date_str]):
        messages.error(request, "Tous les champs sont obligatoires.")
        return redirect(reverse("planning") + redirect_params)

    try:
        shift_date = datetime.strptime(shift_date_str, "%Y-%m-%d").date()
    except ValueError:
        messages.error(
            request, "Date invalide. Veuillez utiliser le format AAAA-MM-JJ."
        )
        return redirect(reverse("planning") + redirect_params)

    try:
        with transaction.atomic():
            # Récupération du service
            service_obj = get_object_or_404(Services, service_name=service_name)
            # Recherche de l'employé via le champ unique nom_prenom
            employee_obj = Personnel.objects.filter(
                nom_prenom__iexact=employee_full_name
            ).first()
            if not employee_obj:
                messages.error(request, "Employé introuvable.")
                return redirect(reverse("planning") + redirect_params)

            if event_id:
                planning_obj = Planning.objects.filter(id=event_id).first()
                if planning_obj:
                    planning_obj.id_service = service_obj
                    planning_obj.shift_date = shift_date
                    planning_obj.shift_type = shift_type
                    planning_obj.employee = employee_obj
                    planning_obj.save()
                    logger.info(f"Mise à jour du planning (ID {event_id}) réussie.")
                else:
                    messages.error(request, "Événement non trouvé pour mise à jour.")
                    return redirect(reverse("planning") + redirect_params)
            else:
                Planning.objects.create(
                    id_service=service_obj,
                    shift_date=shift_date,
                    shift_type=shift_type,
                    employee=employee_obj,
                    # Correction : assigner l'objet Personnel associé à l'utilisateur
                    id_created_par=request.user.personnel,
                    created_at=now(),
                )
                logger.info("Création d'un nouveau planning réussie.")
    except Exception as e:
        logger.exception("Erreur lors de l'enregistrement du planning")
        messages.error(request, "Erreur lors de l'enregistrement du planning.")
        return redirect(reverse("planning") + redirect_params)

    messages.success(request, "Planning enregistré avec succès.")
    return redirect(reverse("planning") + redirect_params)


@permission_required("rh.modifier_planning", raise_exception=True)
def update_event(request):
    """
    Mise à jour d’un événement via déplacement sur le calendrier.
    """
    if request.method != "POST":
        return redirect(reverse("planning"))

    selected_params = build_redirect_params(
        {
            "service": request.POST.get("service", "all"),
            "employee": request.POST.get("employee", "all"),
            "shift": request.POST.get("shift", "all"),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
        }
    )
    event_id = request.POST.get("event_id")
    new_date = request.POST.get("start")
    if not event_id or not new_date:
        return redirect(reverse("planning") + selected_params)
    try:
        with transaction.atomic():
            planning_obj = Planning.objects.filter(id=event_id).first()
            if planning_obj:
                planning_obj.shift_date = new_date
                planning_obj.save()
    except Exception:
        logger.exception("Erreur lors de la mise à jour du planning")
    return redirect(reverse("planning") + selected_params)


@permission_required("rh.supprimer_planning", raise_exception=True)
def delete_event(request, event_id):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"},
            status=405,
            json_dumps_params={"ensure_ascii": False},
        )
    try:
        event = Planning.objects.filter(id=event_id).first()
        if not event:
            return JsonResponse(
                {"success": False, "message": "Événement introuvable"},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )
        event.delete()
        return JsonResponse(
            {"success": True, "message": "Événement supprimé"},
            status=200,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.exception("Erreur suppression")
        return JsonResponse(
            {"success": False, "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@permission_required("rh.exporter_planning", raise_exception=True)
def print_planning(request):
    """
    Export du planning au format PDF avec nettoyage de ressources via BytesIO.
    """
    selected_service = request.GET.get("service", "all")
    selected_shift = request.GET.get("shift", "all")
    selected_employee = request.GET.get("employee", "all")
    selected_start_date = request.GET.get("start_date", "")
    selected_end_date = request.GET.get("end_date", "")

    # Recherche de l'employé si filtré
    employee_obj = None
    if selected_employee != "all":
        employee_obj = Personnel.objects.filter(
            nom_prenom__iexact=selected_employee
        ).first()
        if employee_obj is None:
            return redirect(
                reverse("planning") + "?message=Employé+introuvable.&category=danger"
            )
    # Recherche du service si filtré
    service_obj = None
    if selected_service != "all":
        service_obj = Services.objects.filter(service_name=selected_service).first()

    queryset = Planning.objects.select_related("employee", "id_service").all()
    if service_obj:
        queryset = queryset.filter(id_service=service_obj)
    if selected_shift != "all":
        queryset = queryset.filter(shift_type=selected_shift)
    if employee_obj:
        queryset = queryset.filter(employee=employee_obj)
    if selected_start_date:
        queryset = queryset.filter(shift_date__gte=selected_start_date)
    if selected_end_date:
        queryset = queryset.filter(shift_date__lte=selected_end_date)
    queryset = queryset.order_by("shift_date")

    plannings = [
        {
            "shift_date": p.shift_date,
            "full_name": p.employee.nom_prenom,
            "shift_type": p.shift_type,
            "service": p.id_service.service_name if p.id_service else "",
        }
        for p in queryset.iterator()
    ]
    rendered_html = render(
        request,
        "rh/planning_pdf.html",
        {
            "selected_service": selected_service,
            "selected_shift": selected_shift,
            "selected_employee": selected_employee,
            "selected_start_date": selected_start_date,
            "selected_end_date": selected_end_date,
            "plannings": plannings,
        },
    ).content.decode("utf-8")
    pdf_stream = BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_stream)
    if pisa_status.err:
        logger.error("Erreur lors de la création du PDF")
        return HttpResponse("Erreur lors de la création du PDF", status=500)
    pdf_stream.seek(0)
    response = HttpResponse(pdf_stream, content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=planning.pdf"
    return response


@transaction.atomic
@login_required
def validate_presence(request, event_id):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"}, status=405
        )
    try:
        planning = Planning.objects.get(id=event_id)
        service = planning.id_service  # Récupération du service lié

        # Attribution du prix en fonction du type de shift
        if planning.shift_type.lower() == "jour":
            planning.prix = service.prix_joure
        elif planning.shift_type.lower() == "nuit":
            planning.prix = service.prix_nuit
        elif planning.shift_type.lower() == "24h":
            planning.prix = service.prix_24h
        else:
            # Si le type de shift n'est pas reconnu, vous pouvez gérer une valeur par défaut ou lever une exception
            planning.prix = None

        # Enregistrement des informations de pointage
        planning.pointage_created_at = now()
        planning.pointage_id_created_par = request.user.personnel
        planning.save()
        return JsonResponse(
            {"success": True, "message": "Présence validée avec succès."}
        )
    except Planning.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Planning introuvable."}, status=404
        )
    except Exception as e:
        logger.exception("Erreur lors de la validation de présence")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@transaction.atomic
@login_required
def validate_presence_range(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"}, status=405
        )
    try:
        data = json.loads(request.body)
        date_range = data.get("daterangepicker")
        if not date_range:
            return JsonResponse(
                {"success": False, "message": "La plage de dates est requise."},
                status=400,
            )
        # Supposons que le format est "YYYY-MM-DD - YYYY-MM-DD"
        start_date_str, end_date_str = date_range.split(" - ")
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # Optionnel : Vous pouvez ajouter d'autres filtres (ex. service, employee, shift)
        plannings = Planning.objects.filter(shift_date__range=(start_date, end_date))

        for planning in plannings:
            service = planning.id_service  # Récupération du service lié
            # Attribution du prix en fonction du type de shift
            if planning.shift_type.lower() == "jour":
                planning.prix = service.prix_joure
            elif planning.shift_type.lower() == "nuit":
                planning.prix = service.prix_nuit
            elif planning.shift_type.lower() == "24h":
                planning.prix = service.prix_24h
            else:
                planning.prix = None

            # Mise à jour des informations de pointage
            planning.pointage_created_at = now()
            planning.pointage_id_created_par = request.user.personnel
            planning.save()

        return JsonResponse(
            {"success": True, "message": "Pointages validés avec succès."}
        )
    except Exception as e:
        logger.exception("Erreur lors de la validation multiple de présence")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def get_honoraires_acte(request):
    service_id = request.GET.get("service_id")
    if not service_id:
        return JsonResponse(
            {"success": False, "message": "Service id requis"}, status=400
        )
    try:
        actes = HonorairesActe.objects.filter(id_service=service_id)
        actes_list = [
            {
                "id_acte": acte.id_acte,
                "name_acte": acte.name_acte,
                "prix_acte": str(acte.prix_acte),
            }
            for acte in actes
        ]
        return JsonResponse({"success": True, "data": actes_list})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@transaction.atomic
@login_required
def add_pointage_acte(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée."}, status=405
        )
    try:
        data = json.loads(request.body)
        event_id = data.get("event_id")
        acte_id = data.get("acte_id")
        nbr_actes = data.get("nbr_actes")

        if not all([event_id, acte_id, nbr_actes]):
            return JsonResponse(
                {"success": False, "message": "Données incomplètes."}, status=400
            )

        # Récupération des instances correspondantes
        planning = Planning.objects.get(id=event_id)
        acte = HonorairesActe.objects.get(id_acte=acte_id)

        # Créer ou mettre à jour l'enregistrement dans PointagesActes
        pointage_acte, created = PointagesActes.objects.update_or_create(
            id_planning=planning, id_acte=acte, defaults={"nbr_actes": nbr_actes}
        )

        # Calcul du prix total : prix unitaire de l'acte * nombre d'actes
        # Note : Conversion en Decimal est implicite si vos champs sont du type DecimalField
        total_price = acte.prix_acte * int(nbr_actes)

        # Enregistrement du prix calculé dans le planning (champ prix_acte)
        planning.prix_acte = total_price
        planning.save()

        return JsonResponse(
            {"success": True, "message": "Pointage acte enregistré avec succès."}
        )
    except Exception as e:
        logger.exception("Erreur lors de l'ajout du pointage acte")
        return JsonResponse({"success": False, "message": str(e)}, status=500)
