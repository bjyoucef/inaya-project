# patients/utils.py
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.db import models


def calculate_patient_stats(patient, history):
    """Calcule les statistiques détaillées pour un patient"""
    stats = {
        "total_days": 0,
        "total_cost": Decimal("0.00"),
        "active_admissions": 0,
        "average_stay": 0,
        "last_admission": None,
        "admissions_count": len(history["admissions"]),
    }

    if not history["admissions"]:
        return stats

    total_days = 0
    total_cost = Decimal("0.00")
    active_count = 0
    admission_durations = []

    for admission_data in history["admissions"]:
        # Calculer la durée de séjour
        if admission_data["discharge_date"]:
            duration = (
                admission_data["discharge_date"].date()
                - admission_data["admission_date"].date()
            ).days + 1
        else:
            duration = (
                timezone.now().date() - admission_data["admission_date"].date()
            ).days + 1
            active_count += 1

        total_days += duration
        admission_durations.append(duration)

        # Ajouter le coût
        if admission_data["total_cost"]:
            total_cost += admission_data["total_cost"]

    stats["total_days"] = total_days
    stats["total_cost"] = total_cost
    stats["active_admissions"] = active_count

    # Calculer la durée moyenne
    if admission_durations:
        stats["average_stay"] = sum(admission_durations) / len(admission_durations)

    # Dernière admission
    if history["admissions"]:
        stats["last_admission"] = history["admissions"][0]["admission_date"]

    return stats


def get_patient_dashboard_stats():
    """Statistiques pour le tableau de bord des patients"""
    from .models import Patient, DossierMedical

    today = timezone.now().date()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    # Statistiques de base
    total_patients = Patient.objects.filter(is_active=True).count()

    patients_hospitalises = (
        Patient.objects.filter(
            admissions__is_active=True, admissions__discharge_date__isnull=True
        )
        .distinct()
        .count()
    )

    nouveaux_cette_semaine = Patient.objects.filter(
        created_at__date__gte=week_start
    ).count()

    nouveaux_ce_mois = Patient.objects.filter(created_at__date__gte=month_start).count()

    dossiers_incomplets = DossierMedical.objects.filter(
        models.Q(groupe_sanguin__isnull=True)
        | models.Q(groupe_sanguin="")
        | models.Q(poids__isnull=True)
        | models.Q(taille__isnull=True)
    ).count()

    patients_sans_dossier = Patient.objects.filter(
        is_active=True, dossier_medical__isnull=True
    ).count()

    stats = {
        "total_patients": total_patients,
        "patients_hospitalises": patients_hospitalises,
        "nouveaux_cette_semaine": nouveaux_cette_semaine,
        "nouveaux_ce_mois": nouveaux_ce_mois,
        "dossiers_incomplets": dossiers_incomplets,
        "patients_sans_dossier": patients_sans_dossier,
    }

    # Répartition par groupe sanguin
    groupes_sanguins = {}
    for dossier in DossierMedical.objects.exclude(groupe_sanguin__isnull=True).exclude(
        groupe_sanguin=""
    ):
        groupe = dossier.groupe_sanguin
        groupes_sanguins[groupe] = groupes_sanguins.get(groupe, 0) + 1

    stats["groupes_sanguins"] = groupes_sanguins

    # Patients par tranche d'âge
    age_ranges = {
        "0-18": 0,
        "19-35": 0,
        "36-50": 0,
        "51-65": 0,
        "65+": 0,
        "Non renseigné": 0,
    }

    for patient in Patient.objects.filter(is_active=True):
        age = patient.age
        if age is None:
            age_ranges["Non renseigné"] += 1
        elif age <= 18:
            age_ranges["0-18"] += 1
        elif age <= 35:
            age_ranges["19-35"] += 1
        elif age <= 50:
            age_ranges["36-50"] += 1
        elif age <= 65:
            age_ranges["51-65"] += 1
        else:
            age_ranges["65+"] += 1

    stats["age_ranges"] = age_ranges

    return stats
