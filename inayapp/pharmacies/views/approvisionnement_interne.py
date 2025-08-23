# pharmacies/views/approvisionnement_interne.py

import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from ..models.approvisionnement_interne import DemandeInterne, LigneDemandeInterne
from ..models.produit import Produit
from ..models.stock import Stock
from medical.models.services import Service


@login_required
def liste_demandes_internes(request):
    """Vue pour afficher la liste des demandes internes"""

    # Filtres
    statut_filter = request.GET.get("statut", "")
    priorite_filter = request.GET.get("priorite", "")
    service_filter = request.GET.get("service", "")

    # Base queryset
    demandes = DemandeInterne.objects.select_related(
        "service_demandeur", "pharmacie", "creee_par"
    ).prefetch_related("lignes__produit")

    # Appliquer les filtres
    if statut_filter:
        demandes = demandes.filter(statut=statut_filter)

    if priorite_filter:
        demandes = demandes.filter(priorite=priorite_filter)

    if service_filter:
        demandes = demandes.filter(service_demandeur_id=service_filter)

    # Statistiques
    stats = {
        "total": demandes.count(),
        "en_attente": demandes.filter(statut="EN_ATTENTE").count(),
        "validees": demandes.filter(statut="VALIDEE").count(),
        "preparees": demandes.filter(statut="PREPAREE").count(),
        "livrees": demandes.filter(statut="LIVREE").count(),
        "urgentes": demandes.filter(priorite__in=["URGENTE", "CRITIQUE"]).count(),
    }

    services = Service.objects.all().order_by("name")

    context = {
        "demandes": demandes,
        "stats": stats,
        "services": services,
        "statut_filter": statut_filter,
        "priorite_filter": priorite_filter,
        "service_filter": service_filter,
        "statuts": DemandeInterne.STATUT_CHOICES,
        "priorites": DemandeInterne.PRIORITE_CHOICES,
    }

    return render(request, "approvisionnement/interne/demande_list.html", context)


@login_required
def detail_demande_interne(request, demande_id):
    """Vue pour afficher les détails d'une demande interne"""

    demande = get_object_or_404(
        DemandeInterne.objects.select_related(
            "service_demandeur",
            "pharmacie",
            "creee_par",
            "validee_par",
            "preparee_par",
            "livree_par",
        ).prefetch_related("lignes__produit"),
        id=demande_id,
    )

    # Vérifier les permissions
    user_service = getattr(request.user, "service", None)
    can_validate = (
        request.user.has_perm("pharmacies.can_validate_demande_interne")
        and user_service == demande.pharmacie
    )
    can_prepare = (
        request.user.has_perm("pharmacies.can_prepare_demande_interne")
        and user_service == demande.pharmacie
    )
    can_deliver = (
        request.user.has_perm("pharmacies.can_deliver_demande_interne")
        and user_service == demande.pharmacie
    )

    context = {
        "demande": demande,
        "can_validate": can_validate,
        "can_prepare": can_prepare,
        "can_deliver": can_deliver,
    }

    return render(request, "approvisionnement/interne/demande_detail.html", context)


@login_required
def nouvelle_demande_interne(request):
    """Vue pour créer une nouvelle demande interne"""

    if request.method == "POST":
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                service_demandeur_id = request.POST.get("service_demandeur")
                pharmacie_id = request.POST.get("pharmacie")
                priorite = request.POST.get("priorite", "NORMALE")
                motif_demande = request.POST.get("motif_demande", "")

                # Validation de base
                if not service_demandeur_id or not pharmacie_id:
                    messages.error(
                        request, "Veuillez sélectionner un service et une pharmacie"
                    )
                    return redirect("pharmacies:nouvelle_demande_interne")

                # Créer la demande
                demande = DemandeInterne.objects.create(
                    service_demandeur_id=service_demandeur_id,
                    pharmacie_id=pharmacie_id,
                    priorite=priorite,
                    motif_demande=motif_demande,
                    creee_par=request.user,
                )

                # Traiter les lignes de produits
                produits_data = json.loads(request.POST.get("produits", "[]"))

                for produit_data in produits_data:
                    produit_id = produit_data.get("produit_id")
                    quantite = int(produit_data.get("quantite", 0))
                    observations = produit_data.get("observations", "")

                    if produit_id and quantite > 0:
                        LigneDemandeInterne.objects.create(
                            demande=demande,
                            produit_id=produit_id,
                            quantite_demandee=quantite,
                            observations=observations,
                        )

                messages.success(
                    request, f"Demande {demande.reference} créée avec succès"
                )
                return redirect(
                    "pharmacies:detail_demande_interne", demande_id=demande.id
                )

        except Exception as e:
            messages.error(request, f"Erreur lors de la création: {str(e)}")

    # GET - Afficher le formulaire
    services = Service.objects.all().order_by("name")
    pharmacies = Service.objects.filter(est_pharmacies=True).order_by("name")
    produits = Produit.objects.filter(est_actif=True).order_by("nom")

    context = {
        "services": services,
        "pharmacies": pharmacies,
        "produits": produits,
        "priorites": DemandeInterne.PRIORITE_CHOICES,
    }

    return render(request, "approvisionnement/interne/demande_form.html", context)


@login_required
@permission_required("pharmacies.can_validate_demande_interne")
def valider_demande_interne(request, demande_id):
    """Vue pour valider une demande interne"""

    demande = get_object_or_404(DemandeInterne, id=demande_id)

    if request.method == "POST":
        try:
            # Récupérer les données de validation
            lignes_data = json.loads(request.POST.get("lignes", "[]"))

            # Valider la demande
            demande.valider(request.user, lignes_data)

            messages.success(
                request, f"Demande {demande.reference} validée avec succès"
            )
            return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de la validation: {str(e)}")

    return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)


@login_required
@permission_required("pharmacies.can_validate_demande_interne")
def rejeter_demande_interne(request, demande_id):
    """Vue pour rejeter une demande interne"""

    demande = get_object_or_404(DemandeInterne, id=demande_id)

    if request.method == "POST":
        try:
            motif_rejet = request.POST.get("motif_rejet", "")
            demande.rejeter(request.user, motif_rejet)

            messages.success(request, f"Demande {demande.reference} rejetée")
            return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors du rejet: {str(e)}")

    return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)


@login_required
@permission_required("pharmacies.can_prepare_demande_interne")
def preparer_demande_interne(request, demande_id):
    """Vue pour préparer une demande interne"""

    demande = get_object_or_404(DemandeInterne, id=demande_id)

    if request.method == "POST":
        try:
            demande.preparer(request.user)
            messages.success(
                request, f"Demande {demande.reference} préparée avec succès"
            )

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de la préparation: {str(e)}")

    return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)


@login_required
@permission_required("pharmacies.can_deliver_demande_interne")
def livrer_demande_interne(request, demande_id):
    """Vue pour livrer une demande interne"""

    demande = get_object_or_404(DemandeInterne, id=demande_id)

    if request.method == "POST":
        try:
            demande.livrer(request.user)
            messages.success(request, f"Demande {demande.reference} livrée avec succès")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de la livraison: {str(e)}")

    return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)


@login_required
def annuler_demande_interne(request, demande_id):
    """Vue pour annuler une demande interne"""

    demande = get_object_or_404(DemandeInterne, id=demande_id)

    # Vérifier que l'utilisateur peut annuler (créateur ou admin)
    if demande.creee_par != request.user and not request.user.is_staff:
        messages.error(
            request, "Vous n'avez pas l'autorisation d'annuler cette demande"
        )
        return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)

    if request.method == "POST":
        try:
            motif_annulation = request.POST.get("motif_annulation", "")
            demande.annuler(request.user, motif_annulation)

            messages.success(request, f"Demande {demande.reference} annulée")
            return redirect("pharmacies:liste_demandes_internes")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de l'annulation: {str(e)}")

    return redirect("pharmacies:detail_demande_interne", demande_id=demande.id)


@login_required
@require_http_methods(["GET"])
def api_stock_disponible(request):
    """API pour récupérer le stock disponible d'un produit"""

    produit_id = request.GET.get("produit_id")
    service_id = request.GET.get("service_id")

    if not produit_id or not service_id:
        return JsonResponse({"error": "Paramètres manquants"}, status=400)

    try:
        stock_disponible = Stock.objects.get_stock_disponible(
            produit_id=produit_id, service_id=service_id
        )

        return JsonResponse(
            {
                "stock_disponible": stock_disponible,
                "produit_id": produit_id,
                "service_id": service_id,
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_recherche_produits(request):
    """API pour rechercher des produits"""

    query = request.GET.get("q", "")

    if len(query) < 2:
        return JsonResponse({"produits": []})

    produits = Produit.objects.filter(
        Q(nom__icontains=query) | Q(code_produit__icontains=query), est_actif=True
    ).order_by("nom")[:20]

    produits_data = []
    for produit in produits:
        produits_data.append(
            {
                "id": produit.id,
                "nom": produit.nom,
                "code": produit.code_produit,
                "prix_unitaire": (
                    float(produit.prix_vente) if produit.prix_vente else 0
                ),
            }
        )

    return JsonResponse({"produits": produits_data})


@login_required
def rapport_demandes_internes(request):
    """Vue pour générer un rapport des demandes internes"""

    # Paramètres de filtre
    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")
    service_id = request.GET.get("service")
    statut = request.GET.get("statut")

    # Base queryset
    demandes = DemandeInterne.objects.select_related(
        "service_demandeur", "pharmacie"
    ).prefetch_related("lignes__produit")

    # Appliquer les filtres
    if date_debut:
        demandes = demandes.filter(date_creation__gte=date_debut)
    if date_fin:
        demandes = demandes.filter(date_creation__lte=date_fin)
    if service_id:
        demandes = demandes.filter(service_demandeur_id=service_id)
    if statut:
        demandes = demandes.filter(statut=statut)

    # Statistiques détaillées
    stats = {
        "total_demandes": demandes.count(),
        "par_statut": {},
        "par_priorite": {},
        "par_service": {},
        "delai_moyen_validation": 0,
        "delai_moyen_livraison": 0,
    }

    # Calculer les statistiques par statut
    for statut_code, statut_label in DemandeInterne.STATUT_CHOICES:
        stats["par_statut"][statut_label] = demandes.filter(statut=statut_code).count()

    # Calculer les statistiques par priorité
    for priorite_code, priorite_label in DemandeInterne.PRIORITE_CHOICES:
        stats["par_priorite"][priorite_label] = demandes.filter(
            priorite=priorite_code
        ).count()

    # Calculer les statistiques par service
    services_stats = (
        demandes.values("service_demandeur__nom")
        .annotate(count=Count("id"), total_produits=Sum("lignes__quantite_demandee"))
        .order_by("-count")
    )

    for service_stat in services_stats:
        stats["par_service"][service_stat["service_demandeur__name"]] = {
            "demandes": service_stat["count"],
            "produits": service_stat["total_produits"] or 0,
        }

    context = {
        "demandes": demandes,
        "stats": stats,
        "services": Service.objects.all().order_by("name"),
        "statuts": DemandeInterne.STATUT_CHOICES,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "service_filter": service_id,
        "statut_filter": statut,
    }

    return render(
        request, "approvisionnement/interne/rapport_demandes.html", context
    )
