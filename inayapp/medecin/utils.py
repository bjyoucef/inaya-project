# medecin/utils.py
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Medecin


def search_medecins(query_params):
    """
    Fonction utilitaire pour la recherche et filtrage des médecins
    """
    search_query = query_params.get("search", "").strip()
    specialite_filter = query_params.get("specialite", "").strip()
    disponible_filter = query_params.get("disponible", "").strip()

    # Construction de la requête de base
    medecins = Medecin.objects.select_related("personnel__user").prefetch_related(
        "services"
    )

    # Filtres de recherche
    if search_query:
        medecins = medecins.filter(
            Q(personnel__user__first_name__icontains=search_query)
            | Q(personnel__user__last_name__icontains=search_query)
            | Q(personnel__nom_prenom__icontains=search_query)
            | Q(specialite__icontains=search_query)
            | Q(numero_ordre__icontains=search_query)
        )

    if specialite_filter:
        medecins = medecins.filter(specialite__icontains=specialite_filter)

    if disponible_filter:
        disponible = disponible_filter.lower() == "true"
        medecins = medecins.filter(disponible=disponible)

    return medecins.order_by(
        "personnel__user__last_name", "personnel__user__first_name"
    )


def validate_medecin_data(data, medecin_id=None):
    """
    Fonction de validation des données médecin
    """
    errors = []

    # Validation du personnel
    personnel_id = data.get("personnel_id")
    if not personnel_id:
        errors.append("Le personnel est obligatoire")
    else:
        from rh.models import Personnel

        try:
            personnel = Personnel.objects.get(id=personnel_id)
            # Vérifier si ce personnel appartient à un autre médecin
            existing_medecin = getattr(personnel, "profil_medecin", None)
            if existing_medecin and (
                not medecin_id or existing_medecin.id != medecin_id
            ):
                errors.append("Ce personnel appartient déjà à un autre médecin")
        except Personnel.DoesNotExist:
            errors.append("Personnel inexistant")

    # Validation du numéro d'ordre
    numero_ordre = data.get("numero_ordre", "").strip()
    if numero_ordre:
        query = Medecin.objects.filter(numero_ordre=numero_ordre)
        if medecin_id:
            query = query.exclude(id=medecin_id)
        if query.exists():
            errors.append("Ce numéro d'ordre existe déjà")

    # Validation de la spécialité
    specialite = data.get("specialite", "").strip()
    if specialite and len(specialite) > 100:
        errors.append("La spécialité ne peut pas dépasser 100 caractères")

    # Validation du numéro d'ordre
    if numero_ordre and len(numero_ordre) > 50:
        errors.append("Le numéro d'ordre ne peut pas dépasser 50 caractères")

    return errors


def get_medecin_stats():
    """
    Récupère les statistiques des médecins
    """
    total_medecins = Medecin.objects.count()
    medecins_disponibles = Medecin.objects.filter(disponible=True).count()

    # Statistiques par spécialité
    from django.db.models import Count

    specialites_stats = (
        Medecin.objects.exclude(specialite__isnull=True)
        .exclude(specialite__exact="")
        .values("specialite")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    return {
        "total_medecins": total_medecins,
        "medecins_disponibles": medecins_disponibles,
        "medecins_indisponibles": total_medecins - medecins_disponibles,
        "specialites_populaires": specialites_stats,
    }
