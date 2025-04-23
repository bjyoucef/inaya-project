import logging
from datetime import date, datetime
from datetime import time as datetime_time
from datetime import timedelta

from accueil.models import ConfigDate
from django.core.management import call_command
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, reverse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from utils.utils import get_date_range

from ..models import (Attendance, Employee)

logger = logging.getLogger(__name__)


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

    # Pagination
    page_number = request.GET.get("page", 1)
    paginator = Paginator(employees.order_by('id'),1)
    page = paginator.get_page(page_number)

    report = []
    for employee in page.object_list:

        emp_data = {
            "employee": employee,
            "days": [],
            "totals": {
                "hours": 0,
                "overtime": 0,
                "late": 0,
                "absence": 0,
                "early_leave": 0,
            },
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
                    ref_end_naive = datetime.combine(
                        current_date, employee.reference_end
                    )
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


    return render(request, "rh/pointage_report.html", context)


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
