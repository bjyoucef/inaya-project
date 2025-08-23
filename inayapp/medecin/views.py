from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re
from .models import Medecin
from medical.models import Service


@login_required
def medecin_list(request):
    """Liste des médecins avec recherche et pagination"""
    search_query = request.GET.get("search", "")
    service_filter = request.GET.get("service", "")
    specialite_filter = request.GET.get("specialite", "")

    medecins = Medecin.objects.all().order_by("-created_at")

    # Filtrage par recherche
    if search_query:
        medecins = medecins.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(specialite__icontains=search_query)
        )

    # Filtrage par service
    if service_filter:
        medecins = medecins.filter(services__id=service_filter)

    # Filtrage par spécialité
    if specialite_filter:
        medecins = medecins.filter(specialite__icontains=specialite_filter)

    # Pagination
    paginator = Paginator(medecins, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Pour les filtres
    services = Service.objects.all()
    specialites = (
        Medecin.objects.values_list("specialite", flat=True)
        .distinct()
        .exclude(specialite__isnull=True)
        .exclude(specialite="")
    )

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "service_filter": service_filter,
        "specialite_filter": specialite_filter,
        "services": services,
        "specialites": specialites,
    }

    return render(request, "medecins/medecin_list.html", context)


@login_required
def medecin_detail(request, pk):
    """Détail d'un médecin"""
    medecin = get_object_or_404(Medecin, pk=pk)

    context = {
        "medecin": medecin,
    }

    return render(request, "medecins/medecin_detail.html", context)


@login_required
def medecin_create(request):
    """Créer un nouveau médecin"""
    if request.method == "POST":
        # Récupération des données
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        specialite = request.POST.get("specialite", "").strip()
        telephone = request.POST.get("telephone", "").strip()
        service_ids = request.POST.getlist("services")

        # Validation
        errors = {}

        if not first_name:
            errors["first_name"] = "Le prénom est obligatoire."

        if not last_name:
            errors["last_name"] = "Le nom est obligatoire."

        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors["email"] = "Format d'email invalide."

        if telephone:
            if not re.match(r"^\+?\d{9,15}$", telephone):
                errors["telephone"] = (
                    "Le numéro de téléphone doit être au format +213123456789 (9 à 15 chiffres)."
                )

        if not errors:
            try:
                # Créer le médecin
                medecin = Medecin.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email=email if email else None,
                    specialite=specialite if specialite else None,
                    telephone=telephone if telephone else None,
                    created_by=request.user,
                )

                # Associer les services
                if service_ids:
                    services = Service.objects.filter(id__in=service_ids)
                    medecin.services.set(services)

                messages.success(
                    request, f"Médecin {medecin.nom_complet} créé avec succès."
                )
                return redirect("medecin_detail", pk=medecin.pk)

            except Exception as e:
                messages.error(request, f"Erreur lors de la création : {str(e)}")
        else:
            for field, error in errors.items():
                messages.error(request, error)

    # Pour le formulaire
    services = Service.objects.all()

    context = {
        "services": services,
        "form_data": request.POST if request.method == "POST" else {},
    }

    return render(request, "medecins/medecin_form.html", context)


@login_required
def medecin_update(request, pk):
    """Modifier un médecin"""
    medecin = get_object_or_404(Medecin, pk=pk)

    if request.method == "POST":
        # Récupération des données
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        specialite = request.POST.get("specialite", "").strip()
        telephone = request.POST.get("telephone", "").strip()
        service_ids = request.POST.getlist("services")

        # Validation
        errors = {}

        if not first_name:
            errors["first_name"] = "Le prénom est obligatoire."

        if not last_name:
            errors["last_name"] = "Le nom est obligatoire."

        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors["email"] = "Format d'email invalide."

        if telephone:
            if not re.match(r"^\+?\d{9,15}$", telephone):
                errors["telephone"] = (
                    "Le numéro de téléphone doit être au format +213123456789 (9 à 15 chiffres)."
                )

        if not errors:
            try:
                # Mettre à jour le médecin
                medecin.first_name = first_name
                medecin.last_name = last_name
                medecin.email = email if email else None
                medecin.specialite = specialite if specialite else None
                medecin.telephone = telephone if telephone else None
                medecin.save()

                # Mettre à jour les services
                if service_ids:
                    services = Service.objects.filter(id__in=service_ids)
                    medecin.services.set(services)
                else:
                    medecin.services.clear()

                messages.success(
                    request, f"Médecin {medecin.nom_complet} modifié avec succès."
                )
                return redirect("medecin_detail", pk=medecin.pk)

            except Exception as e:
                messages.error(request, f"Erreur lors de la modification : {str(e)}")
        else:
            for field, error in errors.items():
                messages.error(request, error)

    # Pour le formulaire
    services = Service.objects.all()
    medecin_services = medecin.services.all()

    context = {
        "medecin": medecin,
        "services": services,
        "medecin_services": medecin_services,
        "form_data": (
            request.POST
            if request.method == "POST"
            else {
                "first_name": medecin.first_name,
                "last_name": medecin.last_name,
                "email": medecin.email,
                "specialite": medecin.specialite,
                "telephone": medecin.telephone,
            }
        ),
        "is_update": True,
    }

    return render(request, "medecins/medecin_form.html", context)


@login_required
def medecin_delete(request, pk):
    """Supprimer un médecin"""
    medecin = get_object_or_404(Medecin, pk=pk)

    if request.method == "POST":
        try:
            nom_complet = medecin.nom_complet
            medecin.delete()
            messages.success(request, f"Médecin {nom_complet} supprimé avec succès.")
            return redirect("medecin_list")
        except Exception as e:
            messages.error(request, f"Erreur lors de la suppression : {str(e)}")
            return redirect("medecin_detail", pk=pk)

    context = {
        "medecin": medecin,
    }

    return render(request, "medecins/medecin_confirm_delete.html", context)


@login_required
def medecin_ajax_search(request):
    """Recherche AJAX pour l'autocomplétion"""
    query = request.GET.get("q", "")

    if len(query) < 2:
        return JsonResponse({"results": []})

    medecins = Medecin.objects.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(specialite__icontains=query)
    )[:10]

    results = []
    for medecin in medecins:
        results.append(
            {
                "id": medecin.id,
                "text": str(medecin),
                "nom_complet": medecin.nom_complet,
                "specialite": medecin.specialite,
                "telephone": medecin.telephone,
            }
        )

    return JsonResponse({"results": results})
