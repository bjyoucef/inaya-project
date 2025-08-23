import copy
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import ExpressionWrapper, F, Prefetch, Q, Sum, Value
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views import View
from finance.models import (Convention, PrixSupplementaireConfig, TarifActe,
                            TarifActeConvention)
from medecin.models import Medecin
from medical.models import (ActeKt, ActeProduit, PrestationKt, PrestationActe,
                            PrestationAudit)
from medical.models.prestation_Kt import ActeProduit
from patients.models import Patient
from pharmacies.models import ConsommationProduit, Produit
from utils.utils import services_autorises


@login_required
def audit_list(request):
    """Liste générale des audits avec filtres"""
    audits = PrestationAudit.objects.select_related("prestation", "user").all()

    # Filtres
    search = request.GET.get("search", "")
    champ = request.GET.get("champ", "")
    user_id = request.GET.get("user", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    if search:
        audits = audits.filter(
            Q(prestation__patient__nom__icontains=search)
            | Q(prestation__patient__prenom__icontains=search)
            | Q(user__username__icontains=search)
            | Q(champ__icontains=search)
        )

    if champ:
        audits = audits.filter(champ=champ)

    if user_id:
        audits = audits.filter(user_id=user_id)

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
            audits = audits.filter(date_modification__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            audits = audits.filter(date_modification__lt=date_to_obj)
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(audits, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Données pour les filtres
    champs_disponibles = PrestationAudit.objects.values_list(
        "champ", flat=True
    ).distinct()
    users_disponibles = User.objects.filter(prestationaudit__isnull=False).distinct()

    context = {
        "page_obj": page_obj,
        "search": search,
        "champ": champ,
        "user_id": user_id,
        "date_from": date_from,
        "date_to": date_to,
        "champs_disponibles": champs_disponibles,
        "users_disponibles": users_disponibles,
    }

    return render(request, "audits/audit_list.html", context)


@login_required
def audit_prestation_detail(request, prestation_id):
    """Affiche tous les audits d'une prestation spécifique"""
    prestation = get_object_or_404(PrestationKt, id=prestation_id)
    audits = prestation.audits.select_related("user").all()

    context = {
        "prestation": prestation,
        "audits": audits,
    }

    return render(request, "audits/audit_prestation_detail.html", context)


@login_required
def audit_detail(request, audit_id):
    """Affiche le détail d'un audit spécifique"""
    audit = get_object_or_404(PrestationAudit, id=audit_id)

    # Essayer de parser les JSON pour un meilleur affichage
    parsed_ancienne = None
    parsed_nouvelle = None

    if audit.ancienne_valeur:
        try:
            parsed_ancienne = json.loads(audit.ancienne_valeur)
        except (json.JSONDecodeError, TypeError):
            parsed_ancienne = audit.ancienne_valeur

    if audit.nouvelle_valeur:
        try:
            parsed_nouvelle = json.loads(audit.nouvelle_valeur)
        except (json.JSONDecodeError, TypeError):
            parsed_nouvelle = audit.nouvelle_valeur

    context = {
        "audit": audit,
        "parsed_ancienne": parsed_ancienne,
        "parsed_nouvelle": parsed_nouvelle,
    }

    return render(request, "audits/audit_detail.html", context)
