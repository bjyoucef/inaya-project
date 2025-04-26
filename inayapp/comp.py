# views.py
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDate
from .models import Medecin, PrestationActe


def situation_medecin(request, medecin_id):
    medecin = get_object_or_404(Medecin, pk=medecin_id)

    # Gestion des filtres
    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")

    base_query = PrestationActe.objects.filter(prestation__medecin=medecin)
    if date_debut and date_fin:
        base_query = base_query.filter(
            Q(prestation__date_prestation__date__gte=date_debut)
            & Q(prestation__date_prestation__date__lte=date_fin)
        )

    # Statistiques globales
    stats = {
        "total_honoraires": base_query.aggregate(total=Sum("honoraire_medecin"))[
            "total"
        ]
        or 0,
        "total_patients": base_query.values("prestation__patient").distinct().count(),
        "moyenne_par_patient": base_query.aggregate(avg=Avg("honoraire_medecin"))["avg"]
        or 0,
    }

    # Préparation des données pour les graphiques
    conventions_data = (
        base_query.values("convention__nom")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("-total")
    )

    actes_data = (
        base_query.values("acte__libelle")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("-total")[:10]
    )

    evolution_data = (
        base_query.annotate(date=TruncDate("prestation__date_prestation"))
        .values("date")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("date")
    )

    # Conversion sécurisée des données
    def safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    context = {
        "medecin": medecin,
        "convention_labels": [
            c["convention__nom"] or "Non renseigné" for c in conventions_data
        ],
        "convention_values": [safe_float(c.get("total")) for c in conventions_data],
        "acte_labels": [a["acte__libelle"] or "Acte inconnu" for a in actes_data],
        "acte_values": [safe_float(a.get("total")) for a in actes_data],
        "evolution_dates": [
            e["date"].isoformat() for e in evolution_data if e.get("date")
        ],
        "evolution_totals": [safe_float(e.get("total")) for e in evolution_data],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "total_honoraires": safe_float(stats["total_honoraires"]),
        "total_patients": stats["total_patients"],
        "moyenne_par_patient": safe_float(stats["moyenne_par_patient"]),
    }

    return render(request, "finance/situation.html", context)
