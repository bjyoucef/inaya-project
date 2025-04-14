# views.py
from calendar import c
from collections import defaultdict
import logging
from datetime import date, datetime, time, timedelta
from io import BytesIO
from datetime import datetime, date, timedelta, time as datetime_time
from django.contrib import messages
from django.contrib.auth.decorators import permission_required, login_required
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404, reverse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
from xhtml2pdf import pisa
from django.utils import timezone
from django.views.generic import ListView
from .models import Employee, Attendance, Personnel, Services, Planning
from django.views.decorators.csrf import csrf_exempt
from accueil.models import ConfigDate
from datetime import datetime, timedelta, date, time as datetime_time

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_events(request):
    """
    Retourne les événements sous forme JSON pour un chargement asynchrone.
    """
    try:
        allowed_services = [
            s.service_name
            for s in Services.objects.all()
            if request.user.has_perm(f"rh.view_service_{s.service_name}")
        ]
        qs = Planning.objects.filter(
            employee=request.GET.get("employee"),
            id_service__service_name__in=allowed_services,
            shift_type=request.GET.get("shift"),
            shift_date__range=[request.GET.get("start"), request.GET.get("end")],
        ).select_related("employee", "id_service")
        events = [
            {
                "id": event.id,
                "title": f"{event.employee} - {event.shift_type}",
                "start": event.shift_date.isoformat(),
                "color": event.id_service.color,
                "extendedProps": {"time": event.get_time_display()},
            }
            for event in qs.iterator()
        ]
        return JsonResponse({"events": events})
    except Exception as e:
        logger.exception("Erreur lors du chargement asynchrone des événements")
        return JsonResponse(
            {"events": [], "error": "Erreur lors du chargement"}, status=500
        )


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
    filters = extract_filters(request)

    # Configuration et mise à jour des dates utilisateur
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="planning",
        defaults={"start_date": "2025-01-01", "end_date": "2025-01-01"},
    )
    if filters["start_date"]:
        config.start_date = filters["start_date"]
    if filters["end_date"]:
        config.end_date = filters["end_date"]
    config.save()

    start_date = filters["start_date"] or config.start_date
    end_date = filters["end_date"] or config.end_date

    # Conversion en ISO si nécessaire
    filters["start_date"] = (
        start_date.isoformat() if isinstance(start_date, date) else start_date
    )
    filters["end_date"] = (
        end_date.isoformat() if isinstance(end_date, date) else end_date
    )

    # Construction du filtre de requête
    planning_filter = Q(shift_date__range=[filters["start_date"], filters["end_date"]])
    if filters["service"] != "all":
        planning_filter &= Q(id_service__service_name=filters["service"])
    if filters["employee"] != "all":
        # Recherche sur le champ unique nom_prenom
        employee_name = filters["employee"].strip()
        planning_filter &= Q(employee__nom_prenom__icontains=employee_name)
    if filters["shift"] != "all":
        planning_filter &= Q(shift_type=filters["shift"])

    try:
        plannings = Planning.objects.filter(planning_filter)
    except Exception:
        logger.exception("Erreur lors du filtrage des plannings")
        plannings = []

    # Récupération des services autorisés et des employés actifs
    services = [
        s
        for s in Services.objects.all()
        if request.user.has_perm(f"rh.view_service_{s.service_name}")
    ]
    employees = Personnel.objects.filter(statut_activite=1, use_in_planning=1).order_by(
        "nom_prenom"
    )

    # Préparation des événements pour le calendrier
    service_colors = {s.service_name: s.color for s in services}
    shift_configs = {
        "day": (timedelta(hours=8), timedelta(hours=8)),
        "night": (timedelta(hours=17), timedelta(hours=16)),
        "24H": (timedelta(hours=8), timedelta(hours=24)),
    }
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
                    "title": f"{p.employee} - {p.shift_type} - {p.id_service.service_name}",
                    "start": event_start.isoformat(),
                    "end": event_end.isoformat(),
                    "backgroundColor": service_colors.get(
                        p.id_service.service_name, "gray"
                    ),
                    "borderColor": service_colors.get(
                        p.id_service.service_name, "gray"
                    ),
                }
            )

    context = {
        "employees": employees,
        "services": services,
        "events": events,
        "selected": filters,
        "title": "Plannings",
        "user": request.user,
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
def validate_presence(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"}, status=405
        )
    try:
        planning_id = request.POST.get("planning_id")
        planning = Planning.objects.get(pk=planning_id)
        planning.pointage_created_at = now()
        planning.pointage_id_created_par = (
            request.user.personnel
        )  # Assurez-vous que request.user est lié à un Personnel
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

from datetime import datetime, timedelta, time as datetime_time
from django.shortcuts import render
from django.utils import timezone
from .models import Employee, Attendance


def get_date_range(config):
    """Retourne la plage de dates validée (start_date <= end_date)."""
    start_date, end_date = config.start_date, config.end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def classify_attendances(attendances, employee, current_date):
    """
    Classe les pointages en deux listes : entrées et sorties.
    Si l'employé dispose d'heures de référence, on compare chaque heure de pointage aux heures de référence.
    Sinon, tous les pointages sont considérés comme des entrées.
    """
    entries, exits = [], []
    for att in attendances:
        if employee.reference_start and employee.reference_end:
            att_time = att.check_time.time()
            ref_start = employee.reference_start
            ref_end = employee.reference_end
            # Calcul de la différence en secondes avec l'heure de début et l'heure de fin de référence (dates naïves)
            diff_start = abs(
                (
                    datetime.combine(current_date, att_time)
                    - datetime.combine(current_date, ref_start)
                ).total_seconds()
            )
            diff_end = abs(
                (
                    datetime.combine(current_date, att_time)
                    - datetime.combine(current_date, ref_end)
                ).total_seconds()
            )
            if diff_start < diff_end:
                entries.append(att.check_time)
            else:
                exits.append(att.check_time)
        else:
            entries.append(att.check_time)
    return entries, exits


def build_pairs(
    entries, exits_list, employee, current_date, next_day_records, next_date
):
    """
    Construit les paires (entrée, sortie) en associant chaque entrée à la première sortie ultérieure.
    Si aucune sortie n'est trouvée sur le même jour, on tente de trouver un pointage dans le jour suivant.
    Si toujours rien n'est trouvé et que l'heure de référence de fin est définie, on applique une pénalité de 4 heures.

    Par défaut, si les heures de référence ne sont pas définies, on utilise 08:00 et 16:00.
    """
    default_ref_start = (
        employee.reference_start if employee.reference_start else datetime_time(8, 0)
    )
    default_ref_end = (
        employee.reference_end if employee.reference_end else datetime_time(16, 0)
    )

    pairs = []
    entry_idx, exit_idx = 0, 0
    while entry_idx < len(entries):
        entry = entries[entry_idx]
        exit_time = None
        # Recherche d'une sortie dans la liste exits_list
        while exit_idx < len(exits_list):
            if exits_list[exit_idx] > entry:
                exit_time = exits_list[exit_idx]
                exit_idx += 1
                break
            exit_idx += 1
        # Si aucune sortie n'est trouvée, chercher dans les pointages du jour suivant
        if not exit_time:
            for next_att in next_day_records:
                # On considère les pointages du jour suivant
                if next_att.check_time.date() == next_date:
                    if (
                        default_ref_start
                        and next_att.check_time.time() < default_ref_start
                    ):
                        exit_time = next_att.check_time
                        break
        # Dernier recours : appliquer une pénalité en fixant la sortie à reference_end ± 4 heures
        if not exit_time:
            if default_ref_end > default_ref_start:
                # Jour normal : sortie = reference_end - 4h sur le même jour
                naive_exit = datetime.combine(
                    entry.date(), default_ref_end
                ) - timedelta(hours=4)
                exit_time = timezone.make_aware(naive_exit)
            else:
                # Night shift : la reference_end se situe le jour suivant
                naive_exit = (
                    datetime.combine(entry.date(), default_ref_end)
                    + timedelta(days=1)
                    - timedelta(hours=4)
                )
                exit_time = timezone.make_aware(naive_exit)
        pairs.append((entry, exit_time))
        entry_idx += 1
    return pairs


def format_duration(seconds):
    """Formate une durée (en secondes) au format 'XhYY'. Retourne '-' si la durée est négative ou nulle."""
    if seconds <= 0:
        return "-"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h{minutes:02d}"


def format_minutes(seconds):
    """Formate une durée (en secondes) en minutes suivie de ' min'."""
    minutes = int(seconds // 60)
    return f"{minutes} min" if minutes > 0 else "-"


def attendance_report(request):
    # Récupération du paramètre employé (anviz_id) depuis la requête GET
    employee_id = request.GET.get("employee")

    # Récupération ou création de la configuration liée à l'utilisateur pour la page "pointage"
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="pointage",
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

    # Filtrer sur l'employé si un identifiant est fourni, sinon récupérer uniquement ceux ayant un pointage dans la plage de dates
    if employee_id:
        employees = Employee.objects.filter(
            anviz_id=employee_id,
            attendances__check_time__date__gte=start_date,
            attendances__check_time__date__lte=end_date,
        ).distinct()
    else:
        employees = Employee.objects.filter(
            attendances__check_time__date__gte=start_date,
            attendances__check_time__date__lte=end_date,
        ).distinct()

    report = []
    for employee in employees:
        emp_data = {
            "employee": employee,
            "days": [],
            "totals": {"hours": 0, "overtime": 0, "late": 0, "absence": 0, "early_leave": 0},
        }
        current_date = start_date
        while current_date <= end_date:
            # Récupération des pointages du jour courant
            attendances = Attendance.objects.filter(
                employee=employee, check_time__date=current_date
            ).order_by("check_time")
            # Pointages du jour suivant pour chercher une éventuelle sortie
            next_date = current_date + timedelta(days=1)
            next_day_attendances = Attendance.objects.filter(
                employee=employee, check_time__date=next_date
            ).order_by("check_time")

            # Classement des pointages en entrées et sorties
            entries, exits = classify_attendances(attendances, employee, current_date)
            # Construction des paires d'entrée-sortie
            pairs = build_pairs(
                entries, exits, employee, current_date, next_day_attendances, next_date
            )

            # Calcul du temps total travaillé
            total_seconds = sum(
                (exit_time - entry).total_seconds()
                for entry, exit_time in pairs
                if exit_time
            )
            # Calcul du retard sur la première entrée
            late_seconds = 0
            if employee.reference_start and pairs:
                # On convertit la reference_start en datetime aware
                ref_start_naive = datetime.combine(
                    current_date, employee.reference_start
                )
                ref_start_dt = timezone.make_aware(ref_start_naive)
                if pairs[0][0].time() > employee.reference_start:
                    late_seconds = (pairs[0][0] - ref_start_dt).total_seconds()

            early_leave_seconds = 0
            if employee.reference_end and pairs:
                last_exit = pairs[-1][1]
                if last_exit.time() < employee.reference_end:
                    ref_end_naive = datetime.combine(current_date, employee.reference_end)
                    ref_end_dt = timezone.make_aware(ref_end_naive)
                    early_leave_seconds = (ref_end_dt - last_exit).total_seconds()

            # Durée attendue basée sur les heures de référence (si définies)
            ref_duration = 0
            if employee.reference_start and employee.reference_end:
                ref_start_dt = timezone.make_aware(
                    datetime.combine(current_date, employee.reference_start)
                )
                ref_end_dt = timezone.make_aware(
                    datetime.combine(current_date, employee.reference_end)
                )
                ref_duration = (ref_end_dt - ref_start_dt).total_seconds()

            total_hours = total_seconds / 3600 if total_seconds else 0
            overtime_seconds = (
                max(total_seconds - ref_duration, 0) if ref_duration else 0
            )

            total_hours = total_seconds / 3600
            overtime_hours = overtime_seconds / 3600
            late_minutes = int(late_seconds // 60)

            is_absent = not entries
            if is_absent:
                emp_data["totals"]["absence"] += 1

            day_info = {
                "date": current_date,
                "pairs": [(entry, exit_time) for entry, exit_time in pairs],
                "total": format_duration(total_seconds),
                "overtime": format_duration(overtime_seconds),
                "late_minutes": format_minutes(late_seconds),
                "is_absent": is_absent,
                "entries": entries,
                "early_leave_minutes": format_minutes(early_leave_seconds),
            }

            emp_data["days"].append(day_info)
            emp_data["totals"]["hours"] += total_hours
            emp_data["totals"]["overtime"] += overtime_hours
            emp_data["totals"]["late"] += late_minutes
            emp_data["totals"]["early_leave"] += int(early_leave_seconds // 60)

            current_date += timedelta(days=1)

        # Formatage global des totaux
        emp_data["totals"]["hours_formatted"] = format_duration(
            emp_data["totals"]["hours"] * 3600
        )
        emp_data["totals"]["overtime_formatted"] = format_duration(
            emp_data["totals"]["overtime"] * 3600
        )
        emp_data["totals"]["early_leave_formatted"] = format_minutes(
            emp_data["totals"]["early_leave"] * 60
        )

        report.append(emp_data)

    context = {
        "report": report,
        "employees": employees,
        "request": request,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "selected_employee": employee_id,
    }
    return render(request, "rh/attendance_report.html", context)


@csrf_exempt
def save_reference_hours(request):
    if request.method == "POST":
        emp_id = request.POST.get("employee_id")
        reference_start = request.POST.get("reference_start")
        reference_end = request.POST.get("reference_end")

        try:
            employee = Employee.objects.get(id=emp_id)
            employee.reference_start = reference_start
            employee.reference_end = reference_end
            employee.save()
            return redirect(reverse("attendance_report"))

        except Employee.DoesNotExist:
            return HttpResponse("Employé introuvable", status=404)

    return HttpResponse("Méthode non autorisée", status=405)


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.management import call_command

@require_POST
def sync_attendances(request):

    try:
        # Appeler votre commande de synchronisation
        call_command("sync_attendances")
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def sync_users(request):

    try:
        # Appeler votre commande de synchronisation
        call_command("sync_user")
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
