import json
import logging
from datetime import date, datetime
from datetime import time
from datetime import time as datetime_time
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from utils.utils import get_date_range

from ..models import (Employee, GlobalSalaryConfig, IRGBracket, JourFerie,
                      Personnel, Pointage)

logger = logging.getLogger(__name__)


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


def save_reference_hours(request):
    if request.method == "POST":
        personnel_id = request.POST.get("employee_id")
        reference_start = request.POST.get("reference_start")
        reference_end = request.POST.get("reference_end")

        if not all([personnel_id, reference_start, reference_end]):
            return HttpResponse("Données manquantes", status=400)

        try:
            # Correction du nom du champ de recherche
            personnel = get_object_or_404(Personnel, id_personnel=personnel_id)

            # Vérification de l'existence de l'employee
            if not hasattr(personnel, "employee"):
                return HttpResponse("Aucune fiche pointeuse liée", status=400)

            # Conversion des heures
            employee = personnel.employee
            employee.reference_start = datetime.strptime(
                reference_start, "%H:%M"
            ).time()
            employee.reference_end = datetime.strptime(reference_end, "%H:%M").time()
            employee.save()

            return redirect(reverse("attendance_report"))

        except ValueError:
            return HttpResponse("Format d'heure invalide", status=400)
        except Exception as e:
            return HttpResponse(f"Erreur: {str(e)}", status=500)

    return HttpResponse("Méthode non autorisée", status=405)


def salary_config_view(request):
    try:
        config = GlobalSalaryConfig.get_latest_config()
    except GlobalSalaryConfig.DoesNotExist:
        config = None

    if request.method == "POST":
        return handle_config_save(request)

    context = {
        "config": config,
        "irg_brackets": config.irg_brackets.all(),
    }
    return render(request, "salary_config.html", context)


def handle_config_save(request):
    try:
        with transaction.atomic():
            # Créer/mettre à jour la configuration
            config, created = GlobalSalaryConfig.objects.update_or_create(
                id=1,
                defaults={
                    "cnas_employer_rate": request.POST["cnas_employer_rate"],
                    "cnas_employee_rate": request.POST["cnas_employee_rate"],
                    "daily_meal_allowance": request.POST["daily_meal_allowance"],
                    "daily_transport_allowance": request.POST[
                        "daily_transport_allowance"
                    ],
                    "overtime_hourly_rate": request.POST["overtime_hourly_rate"],
                    "daily_absence_penalty": request.POST["daily_absence_penalty"],
                    "late_minute_penalty": request.POST["late_minute_penalty"],
                    "updated_by": request.user,
                },
            )

            # Vider les anciennes tranches et recréer
            IRGBracket.objects.filter(config=config).delete()
            min_list = request.POST.getlist("min_amount[]")
            max_list = request.POST.getlist("max_amount[]")
            rate_list = request.POST.getlist("tax_rate[]")

            for min_amt, max_amt, rate in zip(min_list, max_list, rate_list):
                IRGBracket.objects.create(
                    config=config,
                    min_amount=Decimal(min_amt),
                    max_amount=Decimal(max_amt) if max_amt else None,
                    tax_rate=Decimal(rate),
                )
            messages.success(request, "Configuration sauvegardée avec succès")

    except Exception as e:
        messages.error(request, f"Erreur lors de l’enregistrement : {e}")

    return redirect("salary_config")


def format_duration(seconds):
    """Formate une durée (en secondes) au format 'XhYY'. Retourne '-' si la durée est négative ou nulle."""
    if seconds <= 0:
        return "-"
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    return f"{hours}h {minutes:02d}m"


def format_minutes(seconds):
    """Formate une durée (en secondes) en minutes suivie de ' min'."""
    minutes = int(seconds / 60)
    return f"{minutes} min" if minutes > 0 else "-"


def rapport_pointage(request):
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

    personnel_id = request.GET.get("personnel")

    employee_prefetch = Prefetch(
        "employee__attendances",
        queryset=Pointage.objects.filter(
            check_time__date__range=(config.start_date, config.end_date)
        ),
    )
    personnels_qs = (
        Personnel.objects.filter(
            employee__attendances__check_time__date__range=(start_date, end_date)
        )
        .prefetch_related(employee_prefetch, "service", "poste")
        .distinct()
    )

    if personnel_id:
        personnels_qs = personnels_qs.filter(id_personnel=personnel_id)

    holidays = JourFerie.objects.filter(
        date__gte=start_date, date__lte=end_date
    ).values_list("date", flat=True)

    report = []
    for personnel in personnels_qs:
        emp_data = initialiser_emp_data(personnel, start_date, end_date, holidays)
        report.append(emp_data)

    context = {
        "report": report,
        "personnels": personnels_qs,
        "request": request,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "selected_employee": int(personnel_id) if personnel_id else None,
    }

    return render(request, "pointage_report.html", context)


def classify_attendances(attendances, employee, current_date):
    """
    Retourne deux listes de Pointage objets (entrées, sorties),
    triées par .check_time et filtrées pour éliminer les points trop proches.
    """
    entries, exits = [], []
    for att in attendances:
        if employee.reference_start and employee.reference_end:
            t = att.check_time.time()
            ref_start, ref_end = employee.reference_start, employee.reference_end

            diff_start = abs(
                (
                    datetime.combine(current_date, t)
                    - datetime.combine(current_date, ref_start)
                ).total_seconds()
            )
            diff_end = abs(
                (
                    datetime.combine(current_date, t)
                    - datetime.combine(current_date, ref_end)
                ).total_seconds()
            )
            if diff_start < diff_end:
                entries.append(att)
            else:
                exits.append(att)
        else:
            entries.append(att)

    # Tri + filtrage “proche” sur .check_time
    entries = filter_close_points(sorted(entries, key=lambda p: p.check_time))
    exits = filter_close_points(sorted(exits, key=lambda p: p.check_time))
    return entries, exits


def filter_close_points(points, threshold=timedelta(hours=2)):
    """
    Garde un seul Pointage toutes les `threshold` secondes.
    points: liste de Pointage triée par .check_time.
    """
    if not points:
        return []
    filtered = [points[0]]
    for p in points[1:]:
        if p.check_time - filtered[-1].check_time >= threshold:
            filtered.append(p)
    return filtered


def build_pairs(entries, exits, employee, current_date, next_day_records, next_date):
    """
    Pour chaque entrée, cherche la sortie correspondante (même jour ou suivant),
    ou génère un SimpleNamespace synthesique en dernier recours.
    """
    default_ref_start = employee.reference_start or datetime_time(8, 0)
    default_ref_end = employee.reference_end or datetime_time(16, 0)

    pairs = []
    exit_idx = 0

    for entry in entries:
        exit_point = None

        # 1) sortie same-day
        while exit_idx < len(exits):
            if exits[exit_idx].check_time > entry.check_time:
                exit_point = exits[exit_idx]
                exit_idx += 1
                break
            exit_idx += 1

        # 2) sinon, cherche au lendemain avant ref_start
        if not exit_point:
            for nxt in next_day_records:
                if (
                    nxt.check_time.date() == next_date
                    and nxt.check_time.time() < default_ref_start
                ):
                    exit_point = nxt
                    break

        # 3) sinon, synthétique: on crée un objet avec .check_time et .ov_validated=False
        if not exit_point:
            if default_ref_end > default_ref_start:
                naive = datetime.combine(
                    entry.check_time.date(), default_ref_end
                ) - timedelta(hours=4)
            else:
                naive = (
                    datetime.combine(entry.check_time.date(), default_ref_end)
                    + timedelta(days=1)
                    - timedelta(hours=4)
                )
            aware = timezone.make_aware(naive)
            exit_point = SimpleNamespace(check_time=aware, ov_validated=False)

        pairs.append((entry, exit_point))

    return pairs


def initialiser_totals():
    """Initialise le dictionnaire des totaux"""
    return {
        "overtime": 0.0,
        "late": 0,
        "absence": 0,
        "holidays_count": 0,
        "holidays_worked": 0,
        "early_leave": 0,
        "public_holiday_overtime": Decimal(0),
        "public_holiday_overtime_amount": Decimal(0),
        "regular_overtime": Decimal(0),
        "regular_overtime_amount": Decimal(0),
        "absence_amount": Decimal(0),
        "late_amount": Decimal(0),
        "early_leave_amount": Decimal(0),
        "penalites": Decimal(0),
        "taux_presence": 0.0,
        "total_working_days_heures": 0.0,
        "taux_horaire": Decimal(0),
        "jours_ouvrables": 0,
        "jours_travailles": 0,
        "hours_formatted": "-",
        "overtime_formatted": "-",
        "late_overtime_formatted": "-",
        "early_overtime_formatted": "-",
        "early_leave_formatted": "-",
        "regular_hours": Decimal(0),
        "regular_hours_formatted": "-",
        "public_holiday_overtime_formatted": "-",
        "early_overtime": 0,
        "late_overtime": 0,
        "early_overtime_amount": Decimal(0),
        "late_overtime_amount": Decimal(0),
        "validated_holiday": Decimal(0),
        "non_validated_holiday": Decimal(0),
        "validated_regular": Decimal(0),
        "non_validated_regular": Decimal(0),
        "validated_regular_formatted": "-",
    }


def initialiser_salaire():
    """Initialise la structure des données salariales"""
    return {
        "salaire_base": Decimal(0),
        "salaire_brut": Decimal(0),
        "salaire_net": Decimal(0),
        "indemnites": {"repas": Decimal(0), "transport": Decimal(0)},
        "deductions": {"irg": Decimal(0), "cnas": Decimal(0)},
    }


def initialiser_emp_data(personnel, start_date, end_date, holidays):
    """Initialise les données d'un employé pour le rapport."""
    employee = personnel.employee
    config = GlobalSalaryConfig.get_latest_config()

    emp_data = {
        "personnel": personnel,
        "days": [],
        "totals": initialiser_totals(),
        "salaire": initialiser_salaire(),
    }

    current_date = start_date
    while current_date <= end_date:
        jour_data = traiter_jour(current_date, employee, holidays)
        emp_data["days"].append(jour_data)
        mettre_a_jour_totaux(emp_data["totals"], jour_data)
        current_date += timedelta(days=1)

    calculer_salaires(emp_data, config)
    return emp_data


def mettre_a_jour_totaux(totals, jour_data):
    """Met à jour les totaux avec les données journalières"""
    # Mise à jour des indicateurs temporels
    totals["regular_hours"] += Decimal(jour_data["total_seconds_w"]) / Decimal(3600)

    totals["late"] += int(jour_data["late_seconds"] / 60)
    totals["early_leave"] += int(jour_data["early_leave_seconds"] / 60)
    totals["early_overtime"] += jour_data["early_overtime_seconds"] 
    totals["late_overtime"] += jour_data["late_overtime_seconds"]

    # Calcul des heures supplémentaires
    if jour_data["is_holiday_weekday"]:
        totals["holidays_count"] += 1
        # Compter les jours fériés effectivement travaillés
    if jour_data["is_holiday_worked"]:
        totals["holidays_worked"] += 1

    # Gestion des absences
    if jour_data["is_absent"]:
        totals["absence"] += 1

    # Comptage des jours ouvrables/travaillés
    if not jour_data["is_weekend"]:
        totals["jours_ouvrables"] += 1
        if not jour_data["is_absent"] and not jour_data["is_holiday"]:
            totals["jours_travailles"] += 1

    if jour_data["is_holiday"] or jour_data["is_weekend"]:
        totals["validated_holiday"] += Decimal(jour_data["validated_overtime"]) / 3600
        totals["non_validated_holiday"] += Decimal(jour_data["non_validated_overtime"]) / 3600
    else:
        totals["validated_regular"] += Decimal(jour_data["validated_overtime"]) / 3600
        totals["non_validated_regular"] += Decimal(jour_data["non_validated_overtime"]) / 3600
        
    print(totals["validated_regular"])
    totals["validation_ratio"] = (
        (
            (totals["validated_regular"] + totals["validated_holiday"])
            / (totals["regular_overtime"] + totals["public_holiday_overtime"])
            * 100
        )
        if (totals["regular_overtime"] + totals["public_holiday_overtime"])
        else 0
    )

def traiter_jour(current_date, employee, holidays):
    """Calcule les données pour un jour spécifique."""
    is_holiday = current_date in holidays
    is_weekend = current_date.weekday() in [4, 5]
    early_overtime = 0
    late_overtime = 0
    # Calcul des heures validées
    validated_overtime = 0
    non_validated_overtime = 0
    early_overtime = 0
    late_overtime = 0
    non_validated_early = 0
    non_validated_late = 0
    
    ref_start = employee.reference_start or datetime_time(8, 0)
    ref_end = employee.reference_end or datetime_time(16, 0)

    attendances = Pointage.objects.filter(
        employee=employee, check_time__date=current_date
    ).order_by("check_time")
    next_day_att = Pointage.objects.filter(
        employee=employee, check_time__date=current_date + timedelta(days=1)
    ).order_by("check_time")

    # Classification des pointages
    entries, exits = classify_attendances(attendances, employee, current_date)
    pairs = build_pairs(
        entries,
        exits,
        employee,
        current_date,
        next_day_att,
        current_date + timedelta(days=1),
    )
    for entry, exit_point in pairs:
        entry_time = entry.check_time.time()
        if entry_time < ref_start:
            entry_dt = datetime.combine(current_date, entry_time)
            ref_start_dt = datetime.combine(current_date, ref_start)
            early_duration = (ref_start_dt - entry_dt).total_seconds()
            if entry.ov_validated:
                early_overtime += early_duration
            else:
                non_validated_early += early_duration

        # Late overtime calculation for each exit (only real Pointage objects)
        if isinstance(exit_point, Pointage):
            exit_time = exit_point.check_time.time()
            exit_date = exit_point.check_time.date()
            ref_end_dt = datetime.combine(current_date, ref_end)
            # Handle cases where exit is on the next day
            if exit_date == current_date:
                exit_dt = datetime.combine(current_date, exit_time)
            else:
                exit_dt = datetime.combine(exit_date, exit_time)
            if exit_dt > ref_end_dt:
                late_duration = (exit_dt - ref_end_dt).total_seconds()
                if exit_point.ov_validated:
                    late_overtime += late_duration
                else:
                    non_validated_late += late_duration

    overtime_seconds = early_overtime + late_overtime + non_validated_early + non_validated_late
    validated_overtime = early_overtime + late_overtime
    non_validated_overtime = non_validated_early + non_validated_late
    
    # Calcul des indicateurs
    is_holiday_worked = False
    if is_holiday and not is_weekend:
        if attendances.exists():
            is_holiday_worked = True
    if is_holiday or is_weekend:
        # Toutes les heures sont supplémentaires les jours fériés/week-end
        total_seconds_w = 0
        validated_overtime = 0
        non_validated_overtime = 0
        for entry, exit_point in pairs:
            if exit_point:
                duration = (exit_point.check_time - entry.check_time).total_seconds()
                if entry.ov_validated or exit_point.ov_validated:
                    validated_overtime += duration
                else:
                    non_validated_overtime += duration
        overtime_seconds = validated_overtime + non_validated_overtime
        
    else:
        total_seconds_w = calculer_heures_reference(pairs, employee, current_date)
        # Calcul des heures supplémentaires avant/après

        if entries:
            # Heures avant la première entrée
            first_entry_time = entries[0].check_time.time()
            if first_entry_time < ref_start:
                early_start = datetime.combine(current_date, first_entry_time)
                ref_start_dt = datetime.combine(current_date, ref_start)
                early_overtime = (ref_start_dt - early_start).total_seconds()

        if exits:
            # Heures après la dernière sortie
            last_exit_time = exits[-1].check_time.time()
            if last_exit_time > ref_end:
                ref_end_dt = datetime.combine(current_date, ref_end)
                late_end = datetime.combine(current_date, last_exit_time)
                late_overtime = (late_end - ref_end_dt).total_seconds()

        overtime_seconds = early_overtime + late_overtime
    return {
        "date": current_date,
        "is_holiday": is_holiday,
        "is_holiday_worked": is_holiday_worked,
        "is_holiday_weekday": is_holiday and not is_weekend,
        "is_weekend": is_weekend,
        "pairs": pairs,
        "total_seconds_w": total_seconds_w,
        "pointages": list(attendances),
        "total": format_duration(total_seconds_w),
        "overtime_seconds": overtime_seconds,
        "overtime": format_duration(overtime_seconds),
        "early_overtime": format_duration(early_overtime),
        "late_overtime": format_duration(late_overtime),
        "early_overtime_seconds": early_overtime / 3600,
        "late_overtime_seconds": late_overtime / 3600,
        "late_seconds": calculer_retard(
            pairs, employee, current_date, is_holiday, is_weekend
        ),
        "late_minutes": format_minutes(
            calculer_retard(pairs, employee, current_date, is_holiday, is_weekend)
        ),
        "early_leave_seconds": calculer_depart_anticipe(pairs, employee, current_date),
        "early_leave_minutes": format_minutes(
            calculer_depart_anticipe(pairs, employee, current_date)
        ),
        "is_absent": not attendances.exists() and not is_holiday and not is_weekend,
        "entries": [e.check_time.time().strftime("%H:%M") for e in entries],
        "exits": [x.check_time.time().strftime("%H:%M") for x in exits],
        
        "validated_overtime": validated_overtime,
        "non_validated_overtime": non_validated_overtime,
        
        "validation_ratio": (
            (validated_overtime / overtime_seconds * 100) if overtime_seconds else 0
        ),
    }


def calculer_heures_reference(pairs, employee, current_date):
    """Calcule le temps de travail effectif dans les heures de référence"""
    ref_start = employee.reference_start or time(8, 0)
    ref_end = employee.reference_end or time(16, 0)

    # Création des datetime objects pour la plage de référence
    ref_start_naive = datetime.combine(current_date, ref_start)
    ref_end_naive = datetime.combine(current_date, ref_end)

    # Gestion des horaires de nuit
    if ref_end < ref_start:
        ref_end_naive += timedelta(days=1)

    # Conversion en objets conscients du fuseau horaire
    ref_start_dt = timezone.make_aware(ref_start_naive)
    ref_end_dt = timezone.make_aware(ref_end_naive)

    total_seconds_w = 0

    for entry, exit_time in pairs:
        if not exit_time:
            continue

        # Déterminer les limites effectives
        debut_effectif = max(entry.check_time, ref_start_dt)
        fin_effective = min(exit_time.check_time, ref_end_dt)

        # Calculer la durée dans la plage de référence
        if fin_effective > debut_effectif:
            duree = (fin_effective - debut_effectif).total_seconds()
            total_seconds_w += duree

    return total_seconds_w


def calculer_retard(pairs, employee, date, is_holiday, is_weekend):
    """Calcule le retard en secondes sur la première entrée"""
    if not pairs or not employee.reference_start:
        return 0
    if is_holiday or is_weekend:
        retard = 0 
    else:
        ref_entry = timezone.make_aware(datetime.combine(date, employee.reference_start))
        first_entry = pairs[0][0].check_time
        retard = (
            max((first_entry - ref_entry).total_seconds(), 0)
            if first_entry > ref_entry
            else 0
        )
    return retard


def calculer_depart_anticipe(pairs, employee, date):
    """Calcule le départ anticipé en secondes sur la dernière sortie"""
    if not pairs or not employee.reference_end:
        return 0

    ref_exit = timezone.make_aware(datetime.combine(date, employee.reference_end))
    last_exit = pairs[-1][1].check_time
    depart_anticipe = (
        max((ref_exit - last_exit).total_seconds(), 0) if last_exit < ref_exit else 0
    )

    return depart_anticipe


def calculer_salaires(emp_data, config):
    """Effectue tous les calculs salariaux."""
    totals = emp_data['totals']
    salaire = emp_data['salaire']
    personnel = emp_data['personnel']

    # 1. Données de base
    ref_start = personnel.employee.reference_start or time(8, 0)
    ref_end = personnel.employee.reference_end or time(16, 0)
    ref_duration = (datetime.combine(date.today(), ref_end) 
                   - datetime.combine(date.today(), ref_start)).total_seconds()
    journalier_hours_ref = Decimal(ref_duration) / Decimal(3600)

    # 2. Calculs des références
    salaire_net_negocie = Decimal(str(personnel.salaire))
    totals['total_ref_days_heures'] = totals['jours_ouvrables'] * journalier_hours_ref

    totals["taux_horaire"] = (
        salaire_net_negocie / totals["total_ref_days_heures"]
        if totals["total_ref_days_heures"] > 0
        else Decimal(0)
    )

    # 3. Indemnités
    salaire["indemnites"]["repas"] = (
        config.daily_meal_allowance / journalier_hours_ref
    ) * totals["regular_hours"]
    salaire["indemnites"]["transport"] = (
        (config.daily_transport_allowance
        / journalier_hours_ref)
        * totals["regular_hours"]
    )

    totals["paid_holidays"] = totals["holidays_count"] - totals["holidays_worked"]

    totals["paid_holidays_amount"] = (
        totals["paid_holidays"] * journalier_hours_ref * totals["taux_horaire"]
    )
    # 4. Salaire de base
    salaire["salaire_base"] = (
        (totals["regular_hours"] * totals["taux_horaire"])
        - salaire["indemnites"]["repas"]
        - salaire["indemnites"]["transport"]
    )

    # 5. Heures supplémentaires
    totals['regular_overtime_amount'] = totals['regular_overtime'] * config.overtime_hourly_rate * totals['taux_horaire']

    totals["early_overtime_amount"] = (
        Decimal(totals["early_overtime"]) * config.overtime_hourly_rate * totals["taux_horaire"]
    )

    totals["late_overtime_amount"] = (
        Decimal(totals["late_overtime"]) * config.overtime_hourly_rate * totals["taux_horaire"]
    )

    totals["public_holiday_overtime_amount"] = (
        totals["public_holiday_overtime"]
        * config.holiday_hourly_rate
        * totals["taux_horaire"]
    )

    # absence_amount totals['absence']
    totals["absence_amount"] = (
        totals["absence"]
        * config.daily_absence_penalty
        * (totals["taux_horaire"] * journalier_hours_ref)
    )

    # late_amount
    totals["late_amount"] = (
        Decimal(totals["late"] / 60)
        * config.late_minute_penalty
        * totals["taux_horaire"]
    )

    # early_leave_amount
    totals["early_leave_amount"] = (
        Decimal(totals["early_leave"] / 60)
        * config.late_minute_penalty
        * totals["taux_horaire"]
    )

    penalty_absence = totals["absence_amount"] - (
        totals["absence"] * (totals["taux_horaire"] * journalier_hours_ref)
    )

    penalty_late = totals["late_amount"] - (
        Decimal(totals["late"] / 60)
        * totals["taux_horaire"]
    )

    penalty_early_leave = totals["early_leave_amount"] - (
        Decimal(totals["early_leave"] / 60)
        * totals["taux_horaire"]
    )
    penalty = penalty_absence + penalty_late + penalty_early_leave
    # 6. Salaire brut
    salaire["salaire_brut"] = (
        salaire["salaire_base"]
        + salaire["indemnites"]["repas"]
        + salaire["indemnites"]["transport"]
        + totals["regular_overtime_amount"]
        + totals["public_holiday_overtime_amount"]
        + totals["paid_holidays_amount"]
    )

    # 7. Déductions
    salaire['deductions']['irg'] = calculer_irg(salaire['salaire_brut'])
    salaire['deductions']['cnas'] = calculer_cnas_employee(salaire['salaire_brut'])

    # 8. Salaire net
    salaire["salaire_net"] = (
        salaire["salaire_base"]
        + salaire["indemnites"]["repas"]
        + salaire["indemnites"]["transport"]
        + totals["regular_overtime_amount"]
        + totals["public_holiday_overtime_amount"]
        + totals["paid_holidays_amount"]
        - penalty
    )

    # 9. Formatage
    totals["validated_regular_formatted"] = format_duration(
        totals["validated_regular"] * 3600
    )
    print(totals["validated_regular_formatted"])
    totals["regular_hours_formatted"] = format_duration(totals["regular_hours"] * 3600)
    totals["overtime_formatted"] = format_duration(totals["regular_overtime"] * 3600)
    totals["early_overtime_formatted"] = format_duration(
        totals["early_overtime"] * 3600
    )
    totals["late_overtime_formatted"] = format_duration(totals["late_overtime"] * 3600)
    totals["public_holiday_overtime_formatted"] = format_duration(
        totals["public_holiday_overtime"] * 3600
    )

    totals['taux_presence'] = round((
        (totals['jours_ouvrables'] - totals['absence']) / totals['jours_ouvrables'] * 100
    ) if totals['jours_ouvrables'] else 0)


def calculer_irg(gross_salary):
    try:
        config = GlobalSalaryConfig.get_latest_config()
        brackets = IRGBracket.objects.filter(config=config).order_by("min_amount")
        remaining_income = Decimal(gross_salary)
        total_tax = Decimal(0)

        for bracket in brackets:
            if remaining_income <= 0:
                break

            bracket_min = Decimal(bracket.min_amount)
            bracket_max = (
                Decimal(bracket.max_amount)
                if bracket.max_amount
                else Decimal("Infinity")
            )
            bracket_rate = Decimal(bracket.tax_rate) / Decimal(100)

            if remaining_income <= bracket_min:
                continue

            taxable_amount = min(remaining_income, bracket_max) - bracket_min
            if taxable_amount > 0:
                total_tax += taxable_amount * bracket_rate
                remaining_income -= taxable_amount

        return round(total_tax, 2)
    except Exception as e:
        logger.error(f"Erreur calcul IRG: {str(e)}")
        return Decimal(0)


def calculer_taux_irg_marginal(brut):
    brackets = IRGBracket.objects.filter(
        config=GlobalSalaryConfig.get_latest_config()
    ).order_by("min_amount")
    for bracket in brackets:
        if brut > bracket.min_amount:
            return Decimal(bracket.tax_rate) / 100
    return Decimal(0)


def calculer_cnas_employer(gross_salary):
    try:
        config = GlobalSalaryConfig.get_latest_config()
        return round(
            Decimal(gross_salary) * (config.cnas_employer_rate / Decimal(100)), 2
        )
    except Exception as e:
        logger.error(f"Erreur calcul CNAS employeur: {str(e)}")
        return Decimal(0)


def calculer_cnas_employee(gross_salary):
    try:
        config = GlobalSalaryConfig.get_latest_config()
        return round(
            Decimal(gross_salary) * (config.cnas_employee_rate / Decimal(100)), 2
        )
    except Exception as e:
        logger.error(f"Erreur calcul CNAS employé: {str(e)}")
        return Decimal(0)


def calculer_repas(jours_travailles):
    try:
        config = GlobalSalaryConfig.get_latest_config()
        return round(config.daily_meal_allowance * Decimal(jours_travailles), 2)
    except Exception as e:
        logger.error(f"Erreur calcul repas: {str(e)}")
        return Decimal(0)


def calculer_transport(jours_travailles):
    try:
        config = GlobalSalaryConfig.get_latest_config()
        return round(config.daily_transport_allowance * Decimal(jours_travailles), 2)
    except Exception as e:
        logger.error(f"Erreur calcul transport: {str(e)}")
        return Decimal(0)


@require_POST
def validate_overtime(request, pointage_id):
    pointage = get_object_or_404(Pointage, id=pointage_id)
    pointage.toggle_validation(request.user)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        return JsonResponse(
            {
                "status": "success",
                "pointage_id": pointage.id,
                "ov_validated": pointage.ov_validated,

            }
        )

    # fallback full page reload
    return redirect(f"{reverse('attendance_report')}?{request.GET.urlencode()}")
