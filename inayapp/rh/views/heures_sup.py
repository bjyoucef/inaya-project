# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from decimal import Decimal
from datetime import datetime
import json

from ..models import DemandeHeuresSupplementaires, Personnel
from django.contrib.auth.models import User


@login_required
def liste_demandes_heures_sup(request):
    """Liste toutes les demandes d'heures supplémentaires avec filtrage"""

    # Récupération des paramètres de filtrage
    statut_filter = request.GET.get("statut", "")
    motif_filter = request.GET.get("motif", "")
    personnel_filter = request.GET.get("personnel", "")
    date_debut_filter = request.GET.get("date_debut", "")
    date_fin_filter = request.GET.get("date_fin", "")
    search = request.GET.get("search", "")

    # Query de base
    demandes = DemandeHeuresSupplementaires.objects.select_related(
        "personnel_demandeur", "personnel_validateur"
    ).all()

    # Application des filtres
    if statut_filter:
        demandes = demandes.filter(statut=statut_filter)

    if motif_filter:
        demandes = demandes.filter(motif=motif_filter)

    if personnel_filter:
        demandes = demandes.filter(personnel_demandeur_id=personnel_filter)

    if date_debut_filter:
        demandes = demandes.filter(date_debut__date__gte=date_debut_filter)

    if date_fin_filter:
        demandes = demandes.filter(date_fin__date__lte=date_fin_filter)

    if search:
        demandes = demandes.filter(
            Q(numero_demande__icontains=search)
            | Q(personnel_demandeur__nom_prenom__icontains=search)
            | Q(description__icontains=search)
        )

    # === PAGINATION ===
    # Nombre d'éléments par page (configurable)
    items_per_page = request.GET.get("per_page", 10)
    try:
        items_per_page = int(items_per_page)
        # Limiter entre 10 et 100 pour éviter les abus
        items_per_page = max(10, min(100, items_per_page))
    except (ValueError, TypeError):
        items_per_page = 25

    paginator = Paginator(demandes, items_per_page)
    page_number = request.GET.get("page",1)

    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        # Si page n'est pas un entier, afficher la première page
        page_obj = paginator.get_page(1)
    except EmptyPage:
        # Si page est hors limite, afficher la dernière page
        page_obj = paginator.get_page(paginator.num_pages)

    # Données pour les filtres
    personnels = Personnel.objects.filter(statut_activite=True).order_by("nom_prenom")
    statuts = DemandeHeuresSupplementaires.STATUT_CHOICES
    motifs = DemandeHeuresSupplementaires.MOTIF_CHOICES

    context = {
        "paginator": paginator,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "items_per_page": items_per_page,
        "total_count": paginator.count,
        
        "personnels": personnels,
        "statuts": statuts,
        "motifs": motifs,
        "filters": {
            "statut": statut_filter,
            "motif": motif_filter,
            "personnel": personnel_filter,
            "date_debut": date_debut_filter,
            "date_fin": date_fin_filter,
            "search": search,
        },
    }

    return render(request, "heures_sup/liste_demandes.html", context)


@login_required
def creer_demande_heures_sup(request):
    """Créer une nouvelle demande d'heures supplémentaires"""

    if request.method == "POST":
        try:
            # Récupération des données du formulaire
            personnel_id = request.POST.get("personnel_demandeur")
            date_debut_str = request.POST.get("date_debut")
            date_fin_str = request.POST.get("date_fin")
            motif = request.POST.get("motif")
            description = request.POST.get("description", "")

            # Validation des données
            if not all([personnel_id, date_debut_str, date_fin_str, motif]):
                messages.error(
                    request, "Tous les champs obligatoires doivent être remplis."
                )
                return redirect("creer_demande_heures_sup")

            # Conversion des dates
            date_debut = datetime.fromisoformat(date_debut_str.replace("Z", "+00:00"))
            date_fin = datetime.fromisoformat(date_fin_str.replace("Z", "+00:00"))

            # Vérification de la cohérence des dates
            if date_fin <= date_debut:
                messages.error(
                    request, "La date de fin doit être postérieure à la date de début."
                )
                return redirect("creer_demande_heures_sup")

            # Récupération du personnel
            personnel = get_object_or_404(Personnel, id_personnel=personnel_id)

            # Calcul du nombre d'heures
            delta = date_fin - date_debut
            nombre_heures = Decimal(str(delta.total_seconds() / 3600)).quantize(
                Decimal("0.01")
            )

            # Création de la demande
            demande = DemandeHeuresSupplementaires.objects.create(
                personnel_demandeur=personnel,
                date_debut=date_debut,
                date_fin=date_fin,
                nombre_heures=nombre_heures,
                motif=motif,
                description=description,
                created_by=request.user,
            )

            messages.success(
                request, f"Demande {demande.numero_demande} créée avec succès."
            )
            return redirect("detail_demande_heures_sup", pk=demande.pk)

        except Exception as e:
            messages.error(
                request, f"Erreur lors de la création de la demande: {str(e)}"
            )

    # GET request - affichage du formulaire
    personnels = Personnel.objects.filter(statut_activite=True).order_by("nom_prenom")
    motifs = DemandeHeuresSupplementaires.MOTIF_CHOICES

    context = {
        "personnels": personnels,
        "motifs": motifs,
    }

    return render(request, "heures_sup/creer_demande.html", context)


@login_required
def detail_demande_heures_sup(request, pk):
    """Afficher les détails d'une demande d'heures supplémentaires"""

    demande = get_object_or_404(
        DemandeHeuresSupplementaires.objects.select_related(
            "personnel_demandeur", "personnel_validateur", "created_by"
        ),
        pk=pk,
    )


    context = {
        "demande": demande,
        "peut_valider": request.user.is_staff or request.user.is_superuser,
    }

    return render(request, "heures_sup/detail_demande.html", context)


@login_required
def modifier_demande_heures_sup(request, pk):
    """Modifier une demande d'heures supplémentaires"""

    demande = get_object_or_404(DemandeHeuresSupplementaires, pk=pk)

    # Vérifier si la demande peut être modifiée
    if not demande.peut_etre_modifiee:
        messages.error(request, "Cette demande ne peut plus être modifiée.")
        return redirect("detail_demande_heures_sup", pk=pk)

    if request.method == "POST":
        try:


            # Récupération des données
            date_debut_str = request.POST.get("date_debut")
            date_fin_str = request.POST.get("date_fin")
            motif = request.POST.get("motif")
            description = request.POST.get("description", "")

            # Validation
            if not all([date_debut_str, date_fin_str, motif]):
                messages.error(
                    request, "Tous les champs obligatoires doivent être remplis."
                )
                return redirect("modifier_demande_heures_sup", pk=pk)

            # Conversion des dates
            date_debut = datetime.fromisoformat(date_debut_str.replace("Z", "+00:00"))
            date_fin = datetime.fromisoformat(date_fin_str.replace("Z", "+00:00"))

            if date_fin <= date_debut:
                messages.error(
                    request, "La date de fin doit être postérieure à la date de début."
                )
                return redirect("modifier_demande_heures_sup", pk=pk)

            # Mise à jour
            demande.date_debut = date_debut
            demande.date_fin = date_fin
            demande.motif = motif
            demande.description = description

            # Recalcul du nombre d'heures
            delta = date_fin - date_debut
            demande.nombre_heures = Decimal(str(delta.total_seconds() / 3600)).quantize(
                Decimal("0.01")
            )

            demande.save()

            messages.success(request, "Demande modifiée avec succès.")
            return redirect("detail_demande_heures_sup", pk=pk)

        except Exception as e:
            messages.error(request, f"Erreur lors de la modification: {str(e)}")

    # GET request
    motifs = DemandeHeuresSupplementaires.MOTIF_CHOICES

    context = {
        "demande": demande,
        "motifs": motifs,
    }

    return render(request, "heures_sup/modifier_demande.html", context)


@login_required
def valider_demande_heures_sup(request, pk):
    """Valider ou refuser une demande d'heures supplémentaires"""

    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(
            request, "Vous n'avez pas les permissions pour valider cette demande."
        )
        return redirect("detail_demande_heures_sup", pk=pk)

    demande = get_object_or_404(DemandeHeuresSupplementaires, pk=pk)

    if request.method == "POST":
        try:
            action = request.POST.get("action")
            commentaire = request.POST.get("commentaire_validation", "")

            if action not in ["approuver", "refuser"]:
                messages.error(request, "Action non valide.")
                return redirect("detail_demande_heures_sup", pk=pk)

            # Sauvegarde de l'ancien statut
            ancien_statut = demande.statut
            nouveau_statut = "approuvee" if action == "approuver" else "refusee"

            # Récupération du personnel validateur
            try:
                personnel_validateur = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                personnel_validateur = None

            # Mise à jour de la demande
            demande.statut = nouveau_statut
            demande.personnel_validateur = personnel_validateur
            demande.date_validation = timezone.now()
            demande.commentaire_validation = commentaire
            demande.save()


            action_text = "approuvée" if action == "approuver" else "refusée"
            messages.success(request, f"Demande {action_text} avec succès.")

        except Exception as e:
            messages.error(request, f"Erreur lors de la validation: {str(e)}")

    return redirect("detail_demande_heures_sup", pk=pk)


@login_required
def annuler_demande_heures_sup(request, pk):
    """Annuler une demande d'heures supplémentaires"""

    demande = get_object_or_404(DemandeHeuresSupplementaires, pk=pk)

    # Vérifier si l'utilisateur peut annuler cette demande
    if not (demande.created_by == request.user or request.user.is_staff):
        messages.error(request, "Vous ne pouvez pas annuler cette demande.")
        return redirect("detail_demande_heures_sup", pk=pk)

    if request.method == "POST":
        if demande.statut == "en_attente":
            ancien_statut = demande.statut
            demande.statut = "annulee"
            demande.save()



            messages.success(request, "Demande annulée avec succès.")
        else:
            messages.error(request, "Cette demande ne peut plus être annulée.")

    return redirect("detail_demande_heures_sup", pk=pk)


@login_required
def calcul_heures_ajax(request):
    """Calculer le nombre d'heures via AJAX"""

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            date_debut_str = data.get("date_debut")
            date_fin_str = data.get("date_fin")

            if not date_debut_str or not date_fin_str:
                return JsonResponse({"error": "Dates manquantes"}, status=400)

            date_debut = datetime.fromisoformat(date_debut_str.replace("Z", "+00:00"))
            date_fin = datetime.fromisoformat(date_fin_str.replace("Z", "+00:00"))

            if date_fin <= date_debut:
                return JsonResponse({"error": "Date de fin invalide"}, status=400)

            delta = date_fin - date_debut
            heures = delta.total_seconds() / 3600

            return JsonResponse(
                {
                    "heures": round(heures, 2),
                    "duree_formatee": f"{int(heures)}h{int((heures % 1) * 60):02d}",
                }
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)
