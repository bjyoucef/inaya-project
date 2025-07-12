# pharmacies/templatetags/approvisionnement_filters.py
from django import template
from django.db.models import Sum, Q
from datetime import datetime, timedelta

register = template.Library()


@register.filter
def sub(value, arg):
    """Soustraction de deux valeurs"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def mul(value, arg):
    """Multiplication de deux valeurs"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def get_item(dictionary, key):
    """Obtenir un élément d'un dictionnaire"""
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.simple_tag
def total_quantite_lignes(lignes):
    """Calculer le total des quantités d'un queryset de lignes"""
    try:
        return lignes.aggregate(total=Sum("quantite_livree"))["total"] or 0
    except:
        return 0


@register.simple_tag
def lots_uniques_count(lignes):
    """Compter le nombre de lots uniques"""
    try:
        return lignes.values("numero_lot").distinct().count()
    except:
        return 0


@register.inclusion_tag("approvisionnement/includes/statut_badge.html")
def statut_badge(statut, statut_choices):
    """Afficher un badge pour le statut"""
    statut_map = {
        "EN_ATTENTE": "warning",
        "BROUILLON": "secondary",
        "VALIDE": "success",
        "CONFIRME": "success",
        "REJETE": "danger",
        "ANNULE": "danger",
        "SERVIE": "info",
        "LIVREE": "info",
        "EN_TRANSIT": "warning",
        "RECU": "success",
        "PARTIEL": "info",
    }

    return {
        "statut": statut,
        "statut_display": dict(statut_choices).get(statut, statut),
        "badge_class": statut_map.get(statut, "secondary"),
    }


@register.simple_tag
def date_warning_class(date_field, warning_days=30):
    """Retourner une classe CSS selon la proximité d'une date"""
    if not date_field:
        return ""

    today = datetime.now().date()
    warning_date = today + timedelta(days=warning_days)

    if date_field < today:
        return "text-danger"
    elif date_field < warning_date:
        return "text-warning"
    else:
        return "text-success"


@register.filter
def days_until(date_field):
    """Calculer le nombre de jours jusqu'à une date"""
    if not date_field:
        return None

    today = datetime.now().date()
    if isinstance(date_field, datetime):
        date_field = date_field.date()

    delta = date_field - today
    return delta.days


@register.simple_tag
def retard_badge(date_prevue, statut):
    """Afficher un badge de retard si nécessaire"""
    if statut not in ["EN_TRANSIT", "PARTIEL"]:
        return ""

    today = datetime.now().date()
    if isinstance(date_prevue, datetime):
        date_prevue = date_prevue.date()

    if date_prevue < today:
        jours_retard = (today - date_prevue).days
        return f'<span class="badge bg-danger ms-1">Retard {jours_retard}j</span>'

    return ""


@register.simple_tag
def pourcentage_completion(quantite_livree, quantite_commandee):
    """Calculer le pourcentage de completion d'une livraison"""
    try:
        if quantite_commandee == 0:
            return 0
        return round((quantite_livree / quantite_commandee) * 100)
    except (TypeError, ZeroDivisionError):
        return 0
