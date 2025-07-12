from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.http import JsonResponse
import json

# Ajoutez ce filtre personnalisé dans templatetags/audit_filters.py
from django import template

register = template.Library()


@register.filter
def pprint(value):
    """Formate un JSON pour un affichage plus lisible"""
    if isinstance(value, dict) or isinstance(value, list):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return value


@register.filter
def get_audit_icon(champ):
    """Retourne l'icône appropriée pour un champ d'audit"""
    icons = {
        "patient": "fas fa-user",
        "medecin": "fas fa-user-md",
        "date_prestation": "fas fa-calendar",
        "statut": "fas fa-flag",
        "observations": "fas fa-comment",
        "prix_total": "fas fa-euro-sign",
        "prix_supplementaire": "fas fa-plus-circle",
        "actes": "fas fa-list",
        "suppression_prestation": "fas fa-trash",
    }
    return icons.get(champ, "fas fa-edit")


@register.filter
def get_audit_color(champ):
    """Retourne la couleur appropriée pour un champ d'audit"""
    colors = {
        "patient": "info",
        "medecin": "info",
        "date_prestation": "warning",
        "statut": "primary",
        "observations": "secondary",
        "prix_total": "success",
        "prix_supplementaire": "success",
        "actes": "warning",
        "suppression_prestation": "danger",
    }
    return colors.get(champ, "info")
