import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
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
from finance.models import Tarif_Gardes
from xhtml2pdf import pisa
from utils.utils import services_autorises
from medical.models import Service
from ..models import (HonorairesActe, Personnel, Planning, PointagesActes, Poste,
                       Shift)

logger = logging.getLogger(__name__)


def extract_filters(request):
    """
    Extrait les filtres de la requête et retourne un dictionnaire avec des valeurs par défaut.
    """
    return {
        "service": request.GET.get("service", "all"),
        "poste": request.GET.get("poste", "all"),
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
        f"?service={filters['service']}&poste={filters['poste']}&shift={filters['shift']}"
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
        defaults={"start_date": date.today(), "end_date": date.today()},
    )

    if filters.get("start_date"):
        config.start_date = filters["start_date"]
    if filters.get("end_date"):
        config.end_date = filters["end_date"]
    config.save()

    # Utiliser les dates des filtres ou celles du config
    start_date = filters.get("start_date") or config.start_date
    end_date = filters.get("end_date") or config.end_date

    # Convertir en ISO pour la comparaison
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
        planning_filter &= Q(service__name=filters["service"])
        pointage_filter &= Q(id_planning__service__name=filters["service"])

    if filters.get("poste", "all") != "all":
        planning_filter &= Q(id_poste__label=filters["poste"])
        pointage_filter &= Q(id_planning__id_poste__label=filters["poste"])

    if filters.get("employee", "all") != "all":
        employee_name = filters["employee"].strip()
        planning_filter &= Q(employee__nom_prenom__icontains=employee_name)
        pointage_filter &= Q(id_planning__employee__nom_prenom__icontains=employee_name)

    if filters.get("shift", "all") != "all":
        planning_filter &= Q(shift__code=filters["shift"])
        pointage_filter &= Q(id_planning__shift__code=filters["shift"])

    try:
        planningsValidees = Planning.objects.select_related(
            "employee", "service"
        ).filter(planning_filter, pointage_created_at__isnull=False,id_decharge__isnull=True)

        plannings = Planning.objects.select_related(
            "employee", "service", "shift"
        ).filter(planning_filter)

        pointages = (
            PointagesActes.objects.select_related(
                "id_planning__employee",
                "id_planning__service",
                "id_acte",
                "id_planning__shift",
            )
            .filter(pointage_filter)
            .order_by("id_planning__shift_date")
        )

    except Exception:
        logger.exception("Erreur lors du filtrage des plannings")
        plannings = Planning.objects.none()
        planningsValidees = Planning.objects.none()
        pointages = PointagesActes.objects.none()

    # Récupération des services autorisés et des employés actifs
    services = services_autorises(request.user)
    employees = Personnel.objects.filter(statut_activite=1, use_in_planning=1).order_by(
        "nom_prenom"
    )
    postes = Poste.objects.all().order_by("label")

    # Préparation des couleurs de services et configuration des shifts
    service_colors = {s.name: s.color for s in services}

    # Construction des événements
    events = []
    for p in plannings.iterator():
        shift = p.shift
        title = f"{p.employee} - {shift.label if shift else 'No Shift'} - {p.id_poste.label}"

        if shift and shift.debut and shift.fin:
            start_time = shift.debut
            end_time = shift.fin
            event_start = datetime.combine(p.shift_date, start_time)
            event_end = datetime.combine(p.shift_date, end_time)
            if end_time < start_time:
                event_end += timedelta(days=1)
        else:
            event_start = datetime.combine(p.shift_date, datetime.min.time())
            event_end = event_start + timedelta(days=1)

        events.append(
            {
                "id": p.id,
                "service_id": p.service.id,
                "id_poste": p.id_poste.id,
                "title": title,
                "start": event_start.isoformat(),
                "end": event_end.isoformat(),
                "backgroundColor": (
                    "gray"
                    if p.pointage_created_at
                    else service_colors.get(p.service.name, "black")
                ),
            }
        )

    # Calculer le total (prix unitaire * nombre d'actes) pour chaque pointage
    for pa in pointages:
        pa.total = pa.id_acte.prix_acte * pa.nbr_actes

    grouped_plannings = defaultdict(
        lambda: {
            "employee": None,
            "prix_total": Decimal(0),
            "prix_acte_total": Decimal(0),
            "pointagesDetail": [],
        }
    )

    for planning in planningsValidees:
        emp_id = planning.employee.id_personnel
        grouped = grouped_plannings[emp_id]
        grouped["employee"] = planning.employee
        grouped["prix_total"] += planning.prix or 0
        grouped["prix_acte_total"] += planning.prix_acte or 0
        grouped["pointagesDetail"].append(
            {
                "service_name": planning.service.name,
                "date_pointage": planning.shift_date.strftime("%Y-%m-%d"),
                "shift": planning.shift.label if planning.shift else "",
                "prix": planning.prix,
                "prix_acte": planning.prix_acte,
            }
        )

    context = {
        "planningsValidees": list(grouped_plannings.values()),
        "employees": employees,
        "postes": postes,
        "services": services,
        "events": events,
        "selected": filters,
        "title": "Plannings",
        "user": request.user,
        "pointages": pointages,
        "shifts": Shift.objects.all(),
    }
    return render(request, "planning.html", context)


@permission_required("rh.creer_planning", raise_exception=True)
def save_planning(request):
    # Extraction centralisée des filtres (GET ou POST)
    filters = (
        {
            "service": request.POST.get("service", "all"),
            "poste": request.POST.get("poste", "all"),
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
    poste_name = request.POST.get("poste")
    employee_full_name = request.POST.get("employee")
    shift = request.POST.get("shift")
    shift_date_str = request.POST.get("date")
    event_id = request.POST.get("event_id")

    if not all([service_name,poste_name, employee_full_name, shift, shift_date_str]):
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
            service_obj = get_object_or_404(Service, name=service_name)
            poste_obj = get_object_or_404(Poste, label=poste_name)
            print("service_obj",service_obj)
            print("poste_obj",poste_obj)
            # Récupération du shift
            shift_code = request.POST.get("shift")
            shift_obj = None
            if shift_code and shift_code != "all":
                shift_obj = get_object_or_404(Shift, code=shift_code)

            # Recherche de l'employé
            employee_obj = Personnel.objects.filter(
                nom_prenom__iexact=employee_full_name
            ).first()
            if not employee_obj:
                messages.error(request, "Employé introuvable.")
                return redirect(reverse("planning") + redirect_params)

            if event_id:
                planning_obj = Planning.objects.filter(id=event_id).first()
                if planning_obj:
                    planning_obj.service = service_obj
                    planning_obj.id_poste = poste_obj
                    planning_obj.shift_date = shift_date
                    planning_obj.shift = shift_obj
                    planning_obj.employee = employee_obj
                    planning_obj.save()
                    logger.info(f"Mise à jour du planning (ID {event_id}) réussie.")
                else:
                    messages.error(request, "Événement non trouvé pour mise à jour.")
                    return redirect(reverse("planning") + redirect_params)
            else:
                Planning.objects.create(
                    service=service_obj,
                    id_poste=poste_obj,
                    shift_date=shift_date,
                    shift=shift_obj,
                    employee=employee_obj,
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
            "poste": request.POST.get("poste", "all"),
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
            planning_obj = Planning.objects.filter(
                id=event_id ,pointage_id_created_par=None
            ).first()
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
        event = Planning.objects.filter(
            id=event_id, id_decharge=None
        ).first()
        if not event:
            return JsonResponse(
                {"success": False, "message": "Événement introuvable"},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )
        event.delete()
        logger.info(f"Événement (ID {event_id}) supprimé avec succès.")


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
        service_obj = Service.objects.filter(name=selected_service).first()

    queryset = Planning.objects.select_related("employee", "service").all()
    if service_obj:
        queryset = queryset.filter(service=service_obj)
    if selected_shift != "all":
        queryset = queryset.filter(shift=selected_shift)
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
            "shift": p.shift,
            "service": p.service.name if p.service else "",
        }
        for p in queryset.iterator()
    ]
    rendered_html = render(
        request,
        "planning_pdf.html",
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
        poste = planning.employee.poste if hasattr(planning.employee, "poste") else None
        service = planning.service
        shift = planning.shift

        # Recherche du tarif
        tarif = Tarif_Gardes.objects.filter(
            poste=poste, service=service, shift=shift
        ).first()
        if not tarif:
            tarif = Tarif_Gardes.objects.filter(
                poste=poste, service=service, shift__isnull=True
            ).first()

        if tarif:
            planning.prix = tarif.prix
        else:
            planning.prix = None

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
                {"success": False, "message": "Plage de dates requise"}, status=400
            )

        start_date_str, end_date_str = date_range.split(" - ")
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        plannings = Planning.objects.filter(shift_date__range=(start_date, end_date))

        for planning in plannings:
            poste = planning.employee.poste
            service = planning.service
            shift = planning.shift

            tarif = Tarif_Gardes.objects.filter(
                poste=poste, service=service, shift=shift
            ).first()

            if not tarif:
                tarif = Tarif_Gardes.objects.filter(
                    poste=poste, service=service, shift__isnull=True
                ).first()

            if tarif:
                planning.prix = tarif.prix
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
    # On récupère maintenant poste_id
    poste_id = request.GET.get("id_poste")
    print("********************************************",poste_id)
    if not poste_id:
        return JsonResponse(
            {"success": False, "message": "Paramètre poste_id requis."}, status=400
        )

    try:
        # On filtre sur id_poste (ForeignKey) avec _id
        actes = HonorairesActe.objects.filter(id_poste_id=poste_id)
        print(actes)
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
        logger.exception("Erreur récupération actes pour poste %s", poste_id)
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

        # Récupération des instances
        planning = Planning.objects.get(id=event_id)
        acte = HonorairesActe.objects.get(id_acte=acte_id)

        # Mise à jour ou création du pointage
        pointage_acte, created = PointagesActes.objects.update_or_create(
            id_planning=planning,
            id_acte=acte,
            defaults={"nbr_actes": int(nbr_actes)},
        )

        # Calcul et enregistrement du prix
        total_price = acte.prix_acte * int(nbr_actes)
        planning.prix_acte = total_price
        planning.save(update_fields=["prix_acte"])

        return JsonResponse(
            {
                "success": True,
                "message": "Pointage acte enregistré.",
                "total_price": str(total_price),
                "created": created,
            }
        )
    except Planning.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Planning introuvable."}, status=404
        )
    except HonorairesActe.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Acte introuvable."}, status=404
        )
    except Exception as e:
        logger.exception("Erreur lors de l'ajout du pointage acte")
        return JsonResponse({"success": False, "message": str(e)}, status=500)
