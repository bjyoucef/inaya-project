import hashlib
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
from django.core.cache import cache
from django.core.management import call_command
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import ExpressionWrapper, F, Prefetch, Q, Sum, Value
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from utils.utils import get_date_range

from ..models import (DemandeHeuresSupplementaires, Employee,
                      GlobalSalaryConfig, IRGBracket, JourFerie, Personnel,
                      Pointage, SalaryAdvanceRequest, ShiftType)

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
    return render(request, "pointage/salary_config.html", context)


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
    # Récupération ou création de la configuration liée à l'utilisateur
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
                pass
    config.save()

    # Obtention d'une plage de dates correcte
    start_date, end_date = get_date_range(config)
    personnel_id = request.GET.get("personnel")

    # === OPTIMISATION: PAGINATION AU NIVEAU DB ===
    # Configuration de la pagination
    items_per_page = request.GET.get("per_page", 1)
    try:
        items_per_page = int(items_per_page)
        items_per_page = max(1, min(100, items_per_page))
    except (ValueError, TypeError):
        items_per_page = 1

    page_number = request.GET.get("page", 1)
    try:
        page_number = int(page_number)
    except (ValueError, TypeError):
        page_number = 1

    # === OPTIMISATION: REQUÊTE PAGINÉE ===
    # Prefetch optimisé pour les pointages
    employee_prefetch = Prefetch(
        "employee__attendances",
        queryset=Pointage.objects.filter(check_time__date__range=(start_date, end_date))
        .select_related()
        .order_by("check_time"),
    )

    # Queryset de base avec optimisations
    base_queryset = (
        Personnel.objects.filter(
            employee__attendances__check_time__date__range=(start_date, end_date)
        )
        .select_related("service", "poste", "employee")
        .prefetch_related(employee_prefetch)
        .distinct()
        .order_by("nom_prenom")  # Ordre cohérent pour la pagination
    )

    # Filtrage par personnel si spécifié
    if personnel_id:
        base_queryset = base_queryset.filter(id_personnel=personnel_id)

    # === PAGINATION DU QUERYSET ===
    paginator = Paginator(base_queryset, items_per_page)

    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    # === CACHE POUR LES JOURS FÉRIÉS ===
    cache_key = f"holidays_{start_date}_{end_date}"
    holidays = cache.get(cache_key)
    if holidays is None:
        holidays = list(
            JourFerie.objects.filter(
                date__gte=start_date, date__lte=end_date
            ).values_list("date", flat=True)
        )
        cache.set(cache_key, holidays, 5)  # Cache 1 heure

    # === TRAITEMENT UNIQUEMENT DES DONNÉES DE LA PAGE COURANTE ===
    report = []
    for personnel in page_obj.object_list:
        # Génération d'une clé de cache pour chaque employé
        cache_key = generate_employee_cache_key(
            personnel.id_personnel, start_date, end_date
        )

        # Tentative de récupération depuis le cache
        emp_data = cache.get(cache_key)
        if emp_data is None:
            emp_data = initialiser_emp_data(personnel, start_date, end_date, holidays)
            # Ajouter les avances
            month = start_date.month
            year = start_date.year
            emp_data["salaire"]["avances"] = personnel.get_monthly_advances(month, year)

            # Cache pour 30 minutes
            cache.set(cache_key, emp_data, 5)

        report.append(emp_data)

    # === RÉCUPÉRATION OPTIMISÉE DE LA LISTE COMPLÈTE POUR LE FILTRE ===
    # Uniquement si on a besoin du dropdown de sélection
    personnels_for_filter = None
    if not personnel_id:  # Seulement si on n'a pas déjà filtré
        personnels_for_filter = (
            Personnel.objects.filter(
                employee__attendances__check_time__date__range=(start_date, end_date)
            )
            .select_related("service", "poste")
            .distinct()
            .order_by("nom_prenom")
            .only("id_personnel", "nom_prenom", "service__name", "poste__label")
        )

    employee_prefetch = Prefetch(
        "employee__attendances",
        queryset=Pointage.objects.filter(check_time__date__range=(start_date, end_date))
        .select_related()
        .order_by("check_time"),
    )
    personnels_all = (
        Personnel.objects.filter(
            employee__attendances__check_time__date__range=(start_date, end_date)
        )
        .select_related("service", "poste", "employee")
        .prefetch_related(employee_prefetch)
        .distinct()
        .order_by("nom_prenom")  # Ordre cohérent pour la pagination
    )

    context = {
        "all_personnels": personnels_all,
        # Données de pagination
        "paginator": paginator,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "items_per_page": items_per_page,
        "total_count": paginator.count,
        # Données du rapport (seulement la page courante)
        "report": report,
        # Données pour les filtres
        "personnels": personnels_for_filter,
        # Paramètres de la requête
        "request": request,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "selected_employee": int(personnel_id) if personnel_id else None,
        # Informations de pagination pour le template
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": (
            page_obj.previous_page_number() if page_obj.has_previous() else None
        ),
        "next_page_number": (
            page_obj.next_page_number() if page_obj.has_next() else None
        ),
    }

    return render(request, "pointage/pointage_report.html", context)


def generate_employee_cache_key(personnel_id, start_date, end_date):
    """Génère une clé de cache unique pour un employé et une période donnée"""
    data = f"{personnel_id}_{start_date}_{end_date}"
    return f"emp_data_{hashlib.md5(data.encode()).hexdigest()}"


def classify_and_pair(attendances_qs, employee, current_date):
    """
    Version améliorée qui gère tous les types de shifts dynamiquement.

    1) Récupère pointages du current_date ET du lendemain si nécessaire
    2) Classe automatiquement selon le type de shift (FIXED/ROTATING/FLEXIBLE/CUSTOM)
    3) Filtre le bruit et construit les paires (entry, exit)
    4) Gère les shifts qui traversent minuit
    """

    attendances_today = list(attendances_qs)

    if not employee.shift_type:
        return [], [], []

    shift_type = employee.shift_type

    # Obtenir les horaires pour aujourd'hui
    hs, he = shift_type.get_hours_for_date(current_date, employee)

    if hs is None or he is None:
        return [], [], []  # Jour de repos

    # Override avec les horaires de référence manuels si définis
    ref_start = getattr(employee, "reference_start", None) or hs
    ref_end = getattr(employee, "reference_end", None) or he

    # Déterminer si le shift traverse minuit
    crosses_midnight = shift_type.is_cross_midnight_shift()
    is_night = shift_type.is_night_shift or crosses_midnight

    # Charger les pointages de demain si nécessaire
    next_date = current_date + timedelta(days=1)
    attendances_tomorrow = []

    load_tomorrow = should_load_tomorrow_attendances(
        shift_type, employee, current_date, next_date, is_night
    )

    if load_tomorrow:
        from ..models import Pointage  # Ajustez l'import selon votre structure

        attendances_tomorrow = list(
            Pointage.objects.filter(employee=employee, check_time__date=next_date)
        )

    # Fusionner et trier tous les pointages
    all_recs = sorted(
        attendances_today + attendances_tomorrow, key=lambda x: x.check_time
    )

    if not all_recs:
        return [], [], []

    # Filtrage global des rebonds
    all_recs = filter_bounces_global(all_recs, min_interval_minutes=120)

    if not all_recs:
        return [], [], []

    # Classification selon le type de shift
    entries, exits = classify_attendances_by_shift_type(
        all_recs, shift_type, employee, current_date, ref_start, ref_end
    )

    # Appliquer le filtrage spécifique des rebonds
    entry_tolerance = shift_type.entry_tolerance_minutes
    exit_tolerance = shift_type.exit_tolerance_minutes

    entries = filter_bounces(entries, entry_tolerance)
    exits = filter_bounces(exits, exit_tolerance)

    # Appariage des entrées et sorties
    pairs = create_entry_exit_pairs(
        entries, exits, employee, current_date, ref_start, ref_end, is_night
    )

    return pairs, entries, exits


def should_load_tomorrow_attendances(
    shift_type, employee, current_date, next_date, is_night
):
    """Détermine s'il faut charger les pointages du lendemain"""
    if is_night or shift_type.is_cross_midnight_shift():
        return True

    if shift_type.category == ShiftType.ROTATING:
        # Vérifier si demain est aussi un jour travaillé
        hs_tomorrow, he_tomorrow = shift_type.get_hours_for_date(next_date, employee)
        return hs_tomorrow is not None and he_tomorrow is not None

    if shift_type.category == ShiftType.FLEXIBLE:
        return True  # Pour les horaires flexibles, toujours charger

    return False


def classify_attendances_by_shift_type(
    all_recs, shift_type, employee, current_date, ref_start, ref_end
):
    """Classifie les pointages selon le type de shift"""
    entries = []
    exits = []

    if (
        shift_type.category == ShiftType.FIXED
        and not shift_type.is_night_shift
        and not shift_type.is_cross_midnight_shift()
    ):
        # FIXED jour classique → alternance simple
        for i, rec in enumerate(all_recs):
            if i % 2 == 0:
                entries.append(rec)
            else:
                exits.append(rec)

    else:
        # Classification par fenêtres temporelles (pour ROTATING, FLEXIBLE, CUSTOM, et shifts de nuit)
        entries, exits = classify_by_time_windows(
            all_recs, shift_type, current_date, ref_start, ref_end
        )

    return entries, exits


def classify_by_time_windows(all_recs, shift_type, current_date, ref_start, ref_end):
    """Classification par fenêtres temporelles"""
    entries = []
    exits = []

    next_date = current_date + timedelta(days=1)
    is_night = shift_type.is_night_shift or shift_type.is_cross_midnight_shift()

    # Définir les bornes de temps de référence
    start_dt = timezone.make_aware(datetime.combine(current_date, ref_start))

    if is_night or shift_type.is_cross_midnight_shift():
        end_dt = timezone.make_aware(datetime.combine(next_date, ref_end))
    else:
        end_dt = timezone.make_aware(datetime.combine(current_date, ref_end))

    # Tolérance personnalisable
    entry_tolerance = timedelta(minutes=shift_type.entry_tolerance_minutes)
    exit_tolerance = timedelta(minutes=shift_type.exit_tolerance_minutes)

    # Point milieu pour la classification temporelle
    mid_time = start_dt + (end_dt - start_dt) / 2

    for rec in all_recs:
        # Fenêtres de tolérance
        in_entry_window = (
            (start_dt - entry_tolerance)
            <= rec.check_time
            <= (start_dt + entry_tolerance)
        )
        in_exit_window = (
            (end_dt - exit_tolerance) <= rec.check_time <= (end_dt + exit_tolerance)
        )

        if in_entry_window and not in_exit_window:
            entries.append(rec)
        elif in_exit_window and not in_entry_window:
            exits.append(rec)
        elif in_entry_window and in_exit_window:
            # Dans les deux fenêtres, choisir la plus proche
            time_to_start = abs((rec.check_time - start_dt).total_seconds())
            time_to_end = abs((rec.check_time - end_dt).total_seconds())

            if time_to_start <= time_to_end:
                entries.append(rec)
            else:
                exits.append(rec)
        else:
            # Classification temporelle basique
            if rec.check_time < mid_time:
                entries.append(rec)
            else:
                exits.append(rec)

    return entries, exits


def filter_bounces_global(pointages_list, min_interval_minutes=240):
    """Filtre les pointages successifs trop rapprochés sur tous les pointages"""
    if not pointages_list:
        return []

    sorted_pointages = sorted(pointages_list, key=lambda x: x.check_time)
    filtered = [sorted_pointages[0]]

    for pointage in sorted_pointages[1:]:
        last_time = filtered[-1].check_time
        time_diff = (pointage.check_time - last_time).total_seconds() / 60

        if time_diff >= min_interval_minutes:
            filtered.append(pointage)

    return filtered


def filter_bounces(pointages_list, min_interval_minutes):
    """Filtre les pointages successifs trop rapprochés"""
    if not pointages_list:
        return []

    sorted_pointages = sorted(pointages_list, key=lambda x: x.check_time)
    filtered = [sorted_pointages[0]]

    for pointage in sorted_pointages[1:]:
        last_time = filtered[-1].check_time
        time_diff = (pointage.check_time - last_time).total_seconds() / 60

        if time_diff >= min_interval_minutes:
            filtered.append(pointage)


    return filtered


def create_entry_exit_pairs(
    entries, exits, employee, current_date, ref_start, ref_end, is_night
):
    """Crée les paires entrée/sortie"""
    pairs = []
    used_exits = set()

    next_date = current_date + timedelta(days=1)

    # Cutoff pour les postes de nuit
    cutoff_next_day = (
        timezone.make_aware(datetime.combine(next_date, ref_start))
        if is_night
        else None
    )

    for entry in entries:
        matched_exit = None

        # Chercher une sortie après cette entrée
        for exit_rec in exits:
            if exit_rec.check_time > entry.check_time and exit_rec.id not in used_exits:

                # Pour les postes de nuit, vérifier le cutoff
                if (
                    is_night
                    and cutoff_next_day
                    and exit_rec.check_time > cutoff_next_day
                ):
                    continue

                matched_exit = exit_rec
                break

        # Si pas de sortie trouvée, créer une sortie factice
        if not matched_exit:
            theoretical_exit_time = calculate_theoretical_exit_time(
                entry, ref_end, current_date, next_date, is_night
            )

            matched_exit = SimpleNamespace(
                check_time=theoretical_exit_time,
                id=None,
                employee=employee,
            )

        pairs.append((entry, matched_exit))
        if hasattr(matched_exit, "id") and matched_exit.id:
            used_exits.add(matched_exit.id)

    return pairs


def calculate_theoretical_exit_time(entry, ref_end, current_date, next_date, is_night):
    """Calcule l'heure de sortie théorique"""
    theoretical_exit_time = entry.check_time.replace(
        hour=ref_end.hour, minute=ref_end.minute, second=0, microsecond=0
    )

    # Pour les postes de nuit ou shifts qui traversent minuit
    if is_night:
        if entry.check_time.date() == current_date:
            theoretical_exit_time = theoretical_exit_time.replace(
                year=next_date.year, month=next_date.month, day=next_date.day
            )

    # Ajuster si nécessaire (par exemple, retirer du temps pour éviter les chevauchements)
    theoretical_exit_time -= timedelta(hours=4)

    return theoretical_exit_time


def initialiser_totals():
    """Initialise le dictionnaire des totaux"""
    return {
        "overtime": 0.0,
        "late": 0,
        "absence": 0,
        "absence_amount": Decimal(0),
        "holidays_count": 0,
        "early_leave": 0,
        "public_holiday_overtime": Decimal(0),
        "public_holiday_overtime_amount": Decimal(0),
        "regular_overtime": Decimal(0),
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
        "late_formatted": "-",
        "early_formatted": "-",
        "early_overtime_formatted": "-",
        "early_leave_formatted": "-",
        "regular_hours": Decimal(0),
        "regular_hours_formatted": "-",
        "public_holiday_overtime_formatted": "-",
        "early_overtime": 0,
        "late_overtime": 0,
        "validated_holiday_formatted": "-",
        "validated_holiday": Decimal(0),
        "validated_regular": Decimal(0),
    }


def initialiser_salaire():
    return {
        "salaire_base": Decimal(0),
        "salaire_brut": Decimal(0),
        "salaire_net": Decimal(0),
        "salaire_net_apres_avance": Decimal(0),  # Nouveau champ
        "avances": Decimal(0),  # Total des avances
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
        "start_date": start_date,
        "end_date": end_date,
    }

    current_date = start_date
    while current_date <= end_date:
        jour_data = traiter_jour(current_date, employee, holidays)
        emp_data["days"].append(jour_data)
        mettre_a_jour_totaux(emp_data["totals"], jour_data)
        current_date += timedelta(days=1)

    calculer_salaires(emp_data, config)
    return emp_data


def get_employee_schedule(employee, date):
    """
    Récupère les horaires de travail pour un employé à une date donnée.
    Prend en compte le ShiftType s'il existe, sinon utilise les horaires de référence.
    """
    if employee.shift_type:
        start_time, end_time = employee.shift_type.get_hours_for_date(date, employee)
        if start_time and end_time:
            return start_time, end_time

    # Fallback vers les horaires de référence de l'employé
    ref_start = employee.reference_start or datetime_time(8, 0)
    ref_end = employee.reference_end or datetime_time(16, 0)
    return ref_start, ref_end


def is_working_day(employee, date, holidays):
    """
    Détermine si un employé doit travailler un jour donné selon son ShiftType.
    """
    is_holiday = date in holidays
    is_weekend = date.weekday() in [4, 5]  # Samedi=5, Dimanche=6

    if employee.shift_type:

        # Vérifier d'abord si l'employé a des horaires définis pour ce jour
        start_time, end_time = employee.shift_type.get_hours_for_date(date, employee)
        has_schedule = start_time is not None and end_time is not None

        # Si pas d'horaires définis pour ce jour, pas de travail
        if not has_schedule:
            return False

        # Si le ShiftType ne considère PAS les week-ends et jours fériés comme travaillables
        if employee.shift_type.considers_weekends_holidays and (
            is_holiday or is_weekend
        ):
            return False

        # Si on arrive ici, l'employé a des horaires et le jour est potentiellement travaillable
        return True

    # Logique par défaut : pas de travail les week-ends et jours fériés
    return not (is_holiday or is_weekend)


def calculer_heures_reference(pairs, employee, current_date, ref_start, ref_end):
    """Calcule le temps de travail effectif dans les heures de référence"""
    # Création des datetime objects pour la plage de référence
    ref_start_naive = datetime.combine(current_date, ref_start)
    ref_end_naive = datetime.combine(current_date, ref_end)

    # Gestion des horaires de nuit (fin avant début)
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


def calculer_retard(pairs, employee, date, is_holiday, is_weekend, ref_start):
    """Calcule le retard en secondes sur la première entrée"""
    if not pairs or not ref_start:
        return 0

    if is_holiday or is_weekend:
        return 0

    ref_entry = timezone.make_aware(datetime.combine(date, ref_start))
    first_entry = pairs[0][0].check_time

    return (
        max((first_entry - ref_entry).total_seconds(), 0)
        if first_entry > ref_entry
        else 0
    )


def calculer_depart_anticipe(pairs, employee, date, ref_end):
    """Calcule le départ anticipé en secondes sur la dernière sortie"""
    if not pairs or not ref_end:
        return 0

    # Gestion des horaires de nuit
    ref_exit_date = date
    if ref_end < (employee.reference_start or datetime_time(8, 0)):
        ref_exit_date = date + timedelta(days=1)

    ref_exit = timezone.make_aware(datetime.combine(ref_exit_date, ref_end))
    last_exit = pairs[-1][1].check_time

    if hasattr(last_exit, "check_time"):
        last_time = last_exit
    else:
        last_time = last_exit  # c'est déjà un datetime

    return max((ref_exit - last_time).total_seconds(), 0) if last_time < ref_exit else 0


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

    # Gestion des absences
    if jour_data["is_absent"]:
        totals["absence"] += 1

    # Comptage des jours ouvrables/travaillés basé sur le ShiftType
    if jour_data["is_expected_work_day"]:
        totals["jours_ouvrables"] += 1
        if not jour_data["is_absent"] and not jour_data["is_holiday"]:
            totals["jours_travailles"] += 1

    # Gestion des heures supplémentaires selon le type de jour
    if jour_data["is_holiday"] or jour_data["is_weekend"]:
        totals["validated_holiday"] += Decimal(jour_data["validated_overtime"]) / 3600

    else:
        totals["validated_regular"] += Decimal(jour_data["validated_overtime"]) / 3600


def check_approved_overtime(personnel, date_travail, overtime_seconds):
    """Vérifie si les heures supplémentaires sont couvertes par une demande approuvée"""
    if overtime_seconds <= 0:
        return 0

    # Rechercher demande approuvée pour ce jour
    demande = DemandeHeuresSupplementaires.objects.filter(
        personnel_demandeur=personnel,
        statut="approuvee",
        date_debut__date__lte=date_travail,
        date_fin__date__gte=date_travail,
    ).first()

    if demande:
        # Convertir les heures approuvées en secondes
        heures_approuvees_sec = float(demande.nombre_heures) * 3600
        validated = min(overtime_seconds, heures_approuvees_sec)

        return validated

    return 0


def traiter_jour(current_date, employee, holidays):
    """Calcule les données pour un jour spécifique en tenant compte du ShiftType."""
    is_holiday = current_date in holidays
    is_weekend = current_date.weekday() in [4, 5]  # Samedi=5, Dimanche=6
    is_expected_work_day = is_working_day(employee, current_date, holidays)

    # Récupérer les horaires pour ce jour
    ref_start, ref_end = get_employee_schedule(employee, current_date)

    # Initialisation des variables
    early_overtime = 0
    late_overtime = 0
    validated_overtime = 0

    attendances = Pointage.objects.filter(
        employee=employee, check_time__date=current_date
    ).order_by("check_time")

    # Classification des pointages
    pairs, entries, exits = classify_and_pair(attendances, employee, current_date)

    # Calcul des heures supplémentaires pour chaque paire entrée/sortie
    for entry, exit_point in pairs:
        entry_time = entry.check_time.time()

        # Heures supplémentaires en début de journée
        if entry_time < ref_start:
            entry_dt = datetime.combine(current_date, entry_time)
            ref_start_dt = datetime.combine(current_date, ref_start)
            early_duration = (ref_start_dt - entry_dt).total_seconds()
            early_overtime += early_duration

        # Heures supplémentaires en fin de journée (seulement pour les vrais objets Pointage)
        if isinstance(exit_point, Pointage):
            exit_time = exit_point.check_time.time()
            exit_date = exit_point.check_time.date()

            # Gérer les horaires de nuit qui s'étendent sur le jour suivant
            if ref_end < ref_start:  # Horaire de nuit
                if exit_date == current_date:
                    # Si la sortie est le même jour et avant minuit
                    if exit_time > ref_start:  # Après l'heure de début
                        ref_end_dt = datetime.combine(
                            current_date + timedelta(days=1), ref_end
                        )
                        exit_dt = datetime.combine(
                            current_date + timedelta(days=1), exit_time
                        )
                    else:
                        ref_end_dt = datetime.combine(current_date, ref_end)
                        exit_dt = datetime.combine(current_date, exit_time)
                else:
                    # Sortie le jour suivant
                    ref_end_dt = datetime.combine(exit_date, ref_end)
                    exit_dt = datetime.combine(exit_date, exit_time)
            else:
                # Horaire normal
                ref_end_dt = datetime.combine(current_date, ref_end)
                if exit_date == current_date:
                    exit_dt = datetime.combine(current_date, exit_time)
                else:
                    exit_dt = datetime.combine(exit_date, exit_time)

            if exit_dt > ref_end_dt:
                late_duration = (exit_dt - ref_end_dt).total_seconds()
                late_overtime += late_duration

    overtime_seconds = early_overtime + late_overtime

    # Calcul des indicateurs spéciaux
    is_holiday_worked = False
    if is_holiday and not is_weekend and attendances.exists():
        is_holiday_worked = True

    # Récupérer le personnel pour vérifier les demandes approuvées
    personnel = getattr(employee, "personnel", None)
    if employee.shift_type:
        # Calcul du temps de travail selon le type de jour
        if employee.shift_type.considers_weekends_holidays and (
                is_holiday or is_weekend or not is_expected_work_day
            ):
            # Pour les jours non-travaillés normalement, toutes les heures sont supplémentaires
            total_seconds_w = 0
            total_overtime = 0

            for entry, exit_point in pairs:
                if exit_point:
                    duration = (exit_point.check_time - entry.check_time).total_seconds()
                    if isinstance(exit_point, Pointage):
                        total_overtime += duration

            # Vérifier les heures supplémentaires approuvées
            if personnel:
                validated_overtime = check_approved_overtime(
                    personnel, current_date, total_overtime
                )
            else:
                validated_overtime = 0

        else:
            # Jour de travail normal
            total_seconds_w = calculer_heures_reference(
                pairs, employee, current_date, ref_start, ref_end
            )

            # Vérifier les heures supplémentaires approuvées
            if personnel:
                validated_overtime = check_approved_overtime(
                    personnel, current_date, overtime_seconds
                )
            else:
                validated_overtime = 0
    else:
        total_seconds_w = 0
        total_overtime = 0
        validated_overtime = 0

    return {
        "date": current_date,
        "is_holiday": is_holiday,
        "is_holiday_worked": is_holiday_worked,
        "is_holiday_weekday": is_holiday and not is_weekend,
        "is_weekend": is_weekend,
        "is_expected_work_day": is_expected_work_day,
        "shift_start": ref_start,
        "shift_end": ref_end,
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
            pairs, employee, current_date, is_holiday, is_weekend, ref_start
        ),
        "late_minutes": format_minutes(
            calculer_retard(
                pairs, employee, current_date, is_holiday, is_weekend, ref_start
            )
        ),
        "early_leave_seconds": calculer_depart_anticipe(
            pairs, employee, current_date, ref_end
        ),
        "early_leave_minutes": format_minutes(
            calculer_depart_anticipe(pairs, employee, current_date, ref_end)
        ),
        "is_absent": not attendances.exists() and is_expected_work_day,
        "entries": [e.check_time.time().strftime("%H:%M") for e in entries],
        "exits": [x.check_time.time().strftime("%H:%M") for x in exits],
        "validated_overtime": validated_overtime,

    }


def calculer_salaires(emp_data, config):
    """Effectue tous les calculs salariaux."""

    totals = emp_data["totals"]
    salaire = emp_data["salaire"]
    personnel = emp_data["personnel"]
    employee = personnel.employee

    # 1. Récupération des heures de référence depuis le ShiftType
    shift_type = employee.shift_type
    if shift_type:
        # Calcul de la durée du shift en heures (sans pause)
        duration_minutes = shift_type.get_shift_duration() * 60
        journalier_hours_ref = Decimal(duration_minutes) / Decimal(60)
    else:
        # Fallback aux heures de l'employé si aucun shift type
        ref_start = employee.reference_start or time(8, 0)
        ref_end = employee.reference_end or time(16, 0)
        ref_duration = (
            datetime.combine(date.today(), ref_end)
            - datetime.combine(date.today(), ref_start)
        ).total_seconds()
        journalier_hours_ref = Decimal(ref_duration) / Decimal(3600)

    # 2. Calculs des références
    salaire_net_negocie = Decimal(str(personnel.salaire))
    totals["total_ref_days_heures"] = totals["jours_ouvrables"] * journalier_hours_ref

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
        config.daily_transport_allowance / journalier_hours_ref
    ) * totals["regular_hours"]
    if employee.shift_type and employee.shift_type.considers_weekends_holidays:
        totals["paid_holidays_amount"] = (
            totals["holidays_count"] * journalier_hours_ref * totals["taux_horaire"]
        )
    else:
        totals["paid_holidays_amount"] = 0
    # 4. Salaire de base
    salaire["salaire_base"] = (
        (totals["regular_hours"] * totals["taux_horaire"])
        - salaire["indemnites"]["repas"]
        - salaire["indemnites"]["transport"]
    )

    # 5. Heures supplémentaires
    # Ajouter les heures supplémentaires validées au calcul
    totals["validated_overtime_amount"] = (
        totals["validated_regular"]
        * config.overtime_hourly_rate
        * totals["taux_horaire"]
    )

    totals["public_holiday_overtime_amount"] = (
        totals["validated_holiday"]
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
        Decimal(totals["late"] / 60) * totals["taux_horaire"]
    )

    penalty_early_leave = totals["early_leave_amount"] - (
        Decimal(totals["early_leave"] / 60) * totals["taux_horaire"]
    )
    penalty = penalty_absence + penalty_late + penalty_early_leave

    # 6. Salaire brut
    salaire["salaire_brut"] = (
        salaire["salaire_base"]
        + salaire["indemnites"]["repas"]
        + salaire["indemnites"]["transport"]
        + totals["validated_overtime_amount"]
        + totals["public_holiday_overtime_amount"]
        + totals["paid_holidays_amount"]
    )

    # 7. Déductions
    salaire["deductions"]["irg"] = calculer_irg(salaire["salaire_brut"])
    salaire["deductions"]["cnas"] = calculer_cnas_employee(salaire["salaire_brut"])

    # 8. Salaire net
    salaire["salaire_net"] = (
        salaire["salaire_base"]
        + salaire["indemnites"]["repas"]
        + salaire["indemnites"]["transport"]
        + totals["validated_overtime_amount"]  # heures supp pointage

        + totals["public_holiday_overtime_amount"]
        + totals["paid_holidays_amount"]
        - penalty
    )
    # Récupérer les avances approuvées pour la période
    advances = SalaryAdvanceRequest.objects.filter(
        personnel=personnel,
        status=SalaryAdvanceRequest.RequestStatus.APPROVED,
        payment_date__gte=emp_data["start_date"],
        payment_date__lte=emp_data["end_date"],
    ).aggregate(total_advances=Sum("amount"))["total_advances"] or Decimal(0)

    # Mettre à jour les données salariales
    salaire["avances"] = advances
    salaire["salaire_net_apres_avance"] = salaire["salaire_net"] - advances
    # 9. Formatage
    totals["late_formatted"] = format_duration(totals["late"] * 60)
    totals["early_formatted"] = format_duration(totals["early_leave"] * 60)

    totals["validated_holiday_formatted"] = format_duration(
        totals["validated_holiday"] * 3600
    )
    totals["validated_regular_formatted"] = format_duration(
        totals["validated_regular"] * 3600
    )

    totals["regular_hours_formatted"] = format_duration(totals["regular_hours"] * 3600)
    totals["overtime_formatted"] = format_duration(totals["regular_overtime"] * 3600)
    totals["early_overtime_formatted"] = format_duration(
        totals["early_overtime"] * 3600
    )
    totals["late_overtime_formatted"] = format_duration(totals["late_overtime"] * 3600)
    totals["public_holiday_overtime_formatted"] = format_duration(
        totals["public_holiday_overtime"] * 3600
    )

    totals["taux_presence"] = (
        (
            (
                (
                    (
                        (totals["jours_ouvrables"] - totals["absence"])
                        * journalier_hours_ref
                    )
                    - Decimal(totals["late"] / 60)
                    - Decimal(totals["early_leave"] / 60)
                    + totals["validated_holiday"]
                    + totals["validated_regular"]
                )
                / (totals["jours_ouvrables"] * journalier_hours_ref)
            )
            * 100
        )
        if totals["jours_ouvrables"]
        else 0
    )


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
