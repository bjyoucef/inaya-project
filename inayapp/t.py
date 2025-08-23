# medical/views/bloc_location.py

import io
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.core.validators import EmailValidator
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from medecin.models import Medecin
from medical.models import PrestationKt
from medical.models.bloc_location import (
    ActeLocation,
    ActeProduitInclus,
    Bloc,
    BlocProduitInclus,
    ConsommationProduitBloc,
    Forfait,
    ForfaitProduitInclus,
    ForfaitActeInclus,
    LocationBloc,
    LocationBlocActe,
)
from patients.models import Patient
from pharmacies.models import Produit
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)


class LocationBlocCreateView(View):
    """Création d'une location de bloc avec gestion automatique des produits inclus"""

    def get(self, request):
        context = {
            "patients": Patient.objects.all(),
            "medecins": Medecin.objects.all(),
            "blocs": Bloc.objects.filter(est_actif=True).order_by("nom_bloc"),
            "forfaits": Forfait.objects.filter(est_actif=True).order_by("nom"),
            "actes_location": ActeLocation.objects.filter(est_actif=True).order_by(
                "nom"
            ),
            "now": timezone.localdate(),
        }

        return render(request, "locations/location_create.html", context)

    def _render_with_errors(self, request, errors):
        context = self.get(request).context_data
        context.update(
            {
                "errors": errors,
                "form_data": request.POST,
            }
        )
        return render(request, "locations/location_create.html", context)

    @transaction.atomic
    def post(self, request):
        # [Le reste du code POST reste identique]
        errors = []
        action = request.POST.get("action", "submit")

        # Récupération des champs obligatoires
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        bloc_id = request.POST.get("bloc")
        nom_acte_raw = (request.POST.get("nom_acte") or "").strip()

        type_tarification = request.POST.get("type_tarification", "DUREE")
        observations = request.POST.get("observations", "").strip()
        date_operation_str = request.POST.get("date_operation")
        heure_operation_str = request.POST.get("heure_operation", "")
        duree_reelle_str = request.POST.get("duree_reelle", "")

        # stocker None côté serveur si la valeur est vide (meilleur que une chaîne vide)
        nom_acte = nom_acte_raw if nom_acte_raw else None

        # NOUVEAUX CHAMPS POUR LA GESTION DES PAIEMENTS
        montant_paye_caisse_str = request.POST.get("montant_paye_caisse", "0")
        notes_paiement = request.POST.get("notes_paiement", "").strip()

        # Validation du montant payé
        montant_paye_caisse = Decimal("0.00")
        if montant_paye_caisse_str:
            try:
                montant_paye_caisse = Decimal(montant_paye_caisse_str)
                if montant_paye_caisse < 0:
                    errors.append("Le montant payé ne peut pas être négatif.")
            except (ValueError, InvalidOperation):
                errors.append("Format du montant payé invalide.")

        # Validation des champs obligatoires
        if not all([patient_id, medecin_id, bloc_id, date_operation_str]):
            errors.append("Tous les champs obligatoires doivent être remplis.")

        # Validation du nom de l'intervention pour DUREE
        if type_tarification == "DUREE" and not nom_acte:
            errors.append(
                "Le nom de l'intervention est obligatoire pour la tarification à la durée."
            )

        # Validation du forfait si tarification forfaitaire
        forfait_id = (
            request.POST.get("forfait") if type_tarification == "FORFAIT" else None
        )

        # Validation du forfait si tarification forfaitaire
        if type_tarification == "FORFAIT" and not forfait_id:
            errors.append(
                "Un forfait doit être sélectionné pour la tarification forfaitaire."
            )

        duree_reelle = None

        # Durée réelle est obligatoire
        if not duree_reelle_str:
            errors.append("La durée réelle est requise pour une opération.")
        else:
            try:
                duree_reelle = int(duree_reelle_str)
                if duree_reelle <= 0:
                    errors.append("La durée réelle doit être positive.")
            except ValueError:
                errors.append("Format de durée réelle invalide.")

        # Conversion de la date
        from django.utils.dateparse import parse_date

        date_operation = parse_date(date_operation_str)
        if date_operation is None:
            errors.append("Format de date invalide (YYYY-MM-DD).")

        # Traitement des heures (optionnelles)
        from datetime import datetime

        heure_operation = None

        if heure_operation_str:
            try:
                heure_operation = datetime.strptime(heure_operation_str, "%H:%M").time()
            except Exception:
                errors.append("Format heure invalide (HH:MM).")

        # Récupération des produits inclus avec quantités réelles ajustées
        produits_inclus_data = []
        produit_inclus_ids = request.POST.getlist("produits_inclus[id][]") or []
        quantites_reelles_inclus = (
            request.POST.getlist("produits_inclus[quantite_reelle][]") or []
        )

        for i, produit_id in enumerate(produit_inclus_ids):
            if not produit_id:
                continue
            try:
                quantite_reelle = (
                    float(quantites_reelles_inclus[i])
                    if i < len(quantites_reelles_inclus) and quantites_reelles_inclus[i]
                    else 0
                )
                if quantite_reelle >= 0:  # Permettre 0 pour marquer comme non consommé
                    produits_inclus_data.append(
                        {"produit_id": produit_id, "quantite_reelle": quantite_reelle}
                    )
            except (ValueError, IndexError):
                errors.append(f"Données invalides pour le produit inclus {i+1}")

        # Récupération des actes supplémentaires avec leurs produits
        actes_data = []
        acte_ids = request.POST.getlist("acte_id[]")
        acte_quantites = request.POST.getlist("acte_quantite[]")
        acte_prix = request.POST.getlist("acte_prix[]")

        for i, acte_id in enumerate(acte_ids):
            if not acte_id:
                continue
            try:
                quantite = (
                    int(acte_quantites[i])
                    if i < len(acte_quantites) and acte_quantites[i]
                    else 1
                )
                prix = (
                    Decimal(acte_prix[i])
                    if i < len(acte_prix) and acte_prix[i]
                    else None
                )
                if quantite > 0:
                    # Récupérer les produits de cet acte
                    acte_produits = []
                    produit_acte_ids = (
                        request.POST.getlist(f"actes[{i}][produits][]") or []
                    )
                    quantites_acte_produits = (
                        request.POST.getlist(f"actes[{i}][quantites_reelles][]") or []
                    )
                    prix_acte_produits = (
                        request.POST.getlist(f"actes[{i}][prix_unitaire][]") or []
                    )

                    for j, prod_id in enumerate(produit_acte_ids):
                        if prod_id:
                            try:
                                qte_reelle = (
                                    float(quantites_acte_produits[j])
                                    if j < len(quantites_acte_produits)
                                    else 0
                                )
                                prix_unit = (
                                    float(prix_acte_produits[j])
                                    if j < len(prix_acte_produits)
                                    else 0
                                )
                                acte_produits.append(
                                    {
                                        "produit_id": prod_id,
                                        "quantite_reelle": qte_reelle,
                                        "prix_unitaire": prix_unit,
                                    }
                                )
                            except (ValueError, IndexError):
                                continue

                    actes_data.append(
                        {
                            "acte_id": acte_id,
                            "quantite": quantite,
                            "prix": prix,
                            "produits": acte_produits,
                        }
                    )
            except (ValueError, IndexError):
                errors.append(f"Données invalides pour l'acte {i+1}")

        # Récupération des produits supplémentaires
        produits_supp = []
        produits_supp_ids = request.POST.getlist("produits_supp[id][]") or []
        quantites_supp = request.POST.getlist("produits_supp[quantite][]") or []
        prix_supp = request.POST.getlist("produits_supp[prix][]") or []

        for i, pid in enumerate(produits_supp_ids):
            if not pid:
                continue
            try:
                q = (
                    float(quantites_supp[i])
                    if i < len(quantites_supp) and quantites_supp[i]
                    else 1
                )
                p = float(prix_supp[i]) if i < len(prix_supp) and prix_supp[i] else 0
                if q > 0:
                    produits_supp.append(
                        {"produit_id": pid, "quantite": q, "prix_unitaire": p}
                    )
            except ValueError:
                errors.append(
                    f"Quantité ou prix invalide pour le produit supplémentaire {i+1}"
                )

        # Si erreurs, retourner au formulaire
        if errors:
            return self._render_with_errors(request, errors)

        # ACTION = SUBMIT : création de la location
        try:
            patient = get_object_or_404(Patient, id=patient_id)
            medecin = get_object_or_404(Medecin, id=medecin_id)
            bloc = get_object_or_404(Bloc, id=bloc_id)
            forfait = get_object_or_404(Forfait, id=forfait_id) if forfait_id else None

            # Créer la location
            location = LocationBloc(
                bloc=bloc,
                patient=patient,
                medecin=medecin,
                date_operation=date_operation,
                heure_operation=heure_operation,
                nom_acte=nom_acte,
                type_tarification=type_tarification,
                forfait=forfait,
                duree_reelle=duree_reelle,
                observations=observations,
                cree_par=request.user,
                # NOUVEAUX CHAMPS
                montant_paye_caisse=montant_paye_caisse,
                notes_paiement=notes_paiement,
            )

            # Le prix et les calculs de paiement seront effectués automatiquement dans le save()
            location.save()

            # NOUVELLE SECTION : GESTION DES ACTES INCLUS DANS LE FORFAIT
            if type_tarification == "FORFAIT" and forfait:
                # Récupérer les actes inclus dans le forfait
                actes_inclus_forfait = ForfaitActeInclus.objects.filter(forfait=forfait)

                # Créer les associations pour les actes inclus dans le forfait
                for acte_inclus in actes_inclus_forfait:
                    LocationBlocActe.objects.create(
                        location=location,
                        acte=acte_inclus.acte,
                        quantite=acte_inclus.quantite,
                        prix_unitaire=acte_inclus.prix_unitaire_inclus,
                    )

                    # Ajouter les produits inclus dans ces actes
                    for acte_produit_inclus in acte_inclus.acte.produits_inclus.all():
                        quantite_totale = (
                            acte_produit_inclus.quantite_standard * acte_inclus.quantite
                        )

                        # Vérifier si une consommation existe déjà pour ce produit
                        consommation_existante = ConsommationProduitBloc.objects.filter(
                            location=location,
                            produit=acte_produit_inclus.produit,
                            source_inclusion="FORFAIT",
                        ).first()

                        if consommation_existante:
                            # Ajouter à la quantité incluse existante
                            consommation_existante.quantite_incluse += quantite_totale
                            consommation_existante.ecart_quantite = (
                                consommation_existante.quantite
                                - consommation_existante.quantite_incluse
                            )
                            consommation_existante.est_inclus = (
                                consommation_existante.ecart_quantite <= 0
                            )
                            consommation_existante.save()
                        else:
                            # Créer une nouvelle consommation avec quantité par défaut
                            ConsommationProduitBloc.objects.create(
                                location=location,
                                produit=acte_produit_inclus.produit,
                                quantite=quantite_totale,  # Par défaut, on consomme ce qui est inclus
                                prix_unitaire=Decimal(
                                    acte_produit_inclus.produit.prix_vente
                                ),
                                est_inclus=True,
                                source_inclusion="FORFAIT",
                                quantite_incluse=quantite_totale,
                                ecart_quantite=0,  # Pas d'écart par défaut
                            )
                            # GESTION DES PRODUITS INCLUS AVEC QUANTITÉS RÉELLES

            # 1. Produits inclus dans le bloc (avec quantités ajustées)
            if type_tarification == "DUREE":
                # Créer un dictionnaire pour les quantités réelles
                quantites_reelles_dict = {
                    int(p["produit_id"]): p["quantite_reelle"]
                    for p in produits_inclus_data
                }

                for bloc_produit in BlocProduitInclus.objects.filter(bloc=bloc):
                    quantite_reelle = quantites_reelles_dict.get(
                        bloc_produit.produit.id,
                        bloc_produit.quantite,  # valeur par défaut si pas spécifiée
                    )

                    # Déterminer si c'est inclus ou un écart
                    ecart = quantite_reelle - bloc_produit.quantite

                    if quantite_reelle > 0:  # Ne créer que si consommé
                        ConsommationProduitBloc.objects.create(
                            location=location,
                            produit=bloc_produit.produit,
                            quantite=quantite_reelle,
                            prix_unitaire=Decimal(bloc_produit.produit.prix_vente),
                            est_inclus=(ecart <= 0),  # Inclus si pas de dépassement
                            source_inclusion="BLOC",
                            quantite_incluse=bloc_produit.quantite,
                            ecart_quantite=ecart,
                        )

            # 2. Produits inclus dans le forfait (avec quantités ajustées)
            if type_tarification == "FORFAIT" and forfait:
                quantites_reelles_dict = {
                    int(p["produit_id"]): p["quantite_reelle"]
                    for p in produits_inclus_data
                }

                # Produits directement inclus dans le forfait
                for forfait_produit in forfait.produits.all():
                    quantite_reelle = quantites_reelles_dict.get(
                        forfait_produit.produit.id,
                        forfait_produit.quantite,  # valeur par défaut
                    )

                    ecart = quantite_reelle - forfait_produit.quantite

                # Vérifier si ce produit existe déjà (via les actes inclus)
                consommation_existante = ConsommationProduitBloc.objects.filter(
                    location=location,
                    produit=forfait_produit.produit,
                    source_inclusion="FORFAIT",
                ).first()

                if consommation_existante:
                    # Mettre à jour avec la quantité réelle et ajouter à l'inclusion
                    consommation_existante.quantite = quantite_reelle
                    consommation_existante.quantite_incluse += forfait_produit.quantite
                    consommation_existante.ecart_quantite = (
                        consommation_existante.quantite
                        - consommation_existante.quantite_incluse
                    )
                    consommation_existante.est_inclus = (
                        consommation_existante.ecart_quantite <= 0
                    )
                    consommation_existante.save()
                else:
                    # Créer nouvelle consommation
                    if quantite_reelle > 0:
                        ConsommationProduitBloc.objects.create(
                            location=location,
                            produit=forfait_produit.produit,
                            quantite=quantite_reelle,
                            prix_unitaire=Decimal(forfait_produit.produit.prix_vente),
                            est_inclus=(ecart <= 0),
                            source_inclusion="FORFAIT",
                            quantite_incluse=forfait_produit.quantite,
                            ecart_quantite=ecart,
                        )

            # 3. Créer les associations avec les actes supplémentaires
            montant_total_actes = Decimal(0)
            for acte_data in actes_data:
                try:
                    acte = ActeLocation.objects.get(id=acte_data["acte_id"])
                    prix_unitaire = (
                        acte_data["prix"] if acte_data["prix"] else acte.prix
                    )

                    # Vérifier si cet acte est déjà inclus dans le forfait
                    if type_tarification == "FORFAIT" and forfait:
                        acte_inclus = ForfaitActeInclus.objects.filter(
                            forfait=forfait, acte=acte
                        ).first()

                        if acte_inclus:
                            # Cet acte est partiellement ou totalement inclus
                            quantite_supplementaire = max(
                                0, acte_data["quantite"] - acte_inclus.quantite
                            )
                            if quantite_supplementaire > 0:
                                # Créer seulement pour la partie supplémentaire
                                location_acte = LocationBlocActe.objects.create(
                                    location=location,
                                    acte=acte,
                                    quantite=quantite_supplementaire,
                                    prix_unitaire=prix_unitaire,
                                )
                                montant_total_actes += location_acte.prix_total
                            # Les produits de la partie incluse sont déjà gérés plus haut
                            continue

                        # Créer l'association acte-location (acte entièrement supplémentaire)
                        location_acte = LocationBlocActe.objects.create(
                            location=location,
                            acte=acte,
                            quantite=acte_data["quantite"],
                            prix_unitaire=prix_unitaire,
                        )
                        montant_total_actes += location_acte.prix_total

                    # 4. Ajouter les produits de l'acte avec quantités réelles
                    for prod_acte_data in acte_data["produits"]:
                        try:
                            produit = Produit.objects.get(
                                id=prod_acte_data["produit_id"]
                            )
                            quantite_reelle = prod_acte_data["quantite_reelle"]

                            # Vérifier si c'est un produit inclus dans l'acte
                            try:
                                acte_produit_inclus = ActeProduitInclus.objects.get(
                                    acte=acte, produit=produit
                                )
                                # Quantité incluse = quantité standard * nombre d'actes
                                quantite_incluse = (
                                    acte_produit_inclus.quantite_standard
                                    * acte_data["quantite"]
                                )
                                ecart = quantite_reelle - quantite_incluse
                                est_inclus = ecart <= 0
                                source = "ACTE"
                            except ActeProduitInclus.DoesNotExist:
                                # Produit ajouté manuellement à l'acte
                                quantite_incluse = 0
                                ecart = quantite_reelle
                                est_inclus = False
                                source = "ACTE_SUPPLEMENTAIRE"

                            if quantite_reelle > 0:
                                ConsommationProduitBloc.objects.create(
                                    location=location,
                                    produit=produit,
                                    quantite=quantite_reelle,
                                    prix_unitaire=Decimal(
                                        prod_acte_data["prix_unitaire"]
                                    ),
                                    est_inclus=est_inclus,
                                    source_inclusion=source,
                                    quantite_incluse=quantite_incluse,
                                    ecart_quantite=ecart,
                                    acte_associe=location_acte,  # Lien vers l'acte
                                )

                        except Produit.DoesNotExist:
                            logger.error(
                                f"Produit d'acte introuvable: {prod_acte_data['produit_id']}"
                            )
                            continue

                except ActeLocation.DoesNotExist:
                    logger.error(f"Acte introuvable: {acte_data['acte_id']}")
                    continue

            # 5. Ajouter les produits supplémentaires (non inclus)
            for ps in produits_supp:
                try:
                    prod = Produit.objects.get(id=ps["produit_id"])
                    ConsommationProduitBloc.objects.create(
                        location=location,
                        produit=prod,
                        quantite=ps["quantite"],
                        prix_unitaire=Decimal(ps["prix_unitaire"]),
                        est_inclus=False,
                        source_inclusion="SUPPLEMENTAIRE",
                        quantite_incluse=0,
                        ecart_quantite=ps["quantite"],  # Tout est en écart
                    )
                    logger.info(
                        f"Ajout produit supplémentaire: {prod.nom} x{ps['quantite']}"
                    )
                except Produit.DoesNotExist:
                    logger.error(
                        f"Produit supplémentaire introuvable: {ps['produit_id']}"
                    )
                    continue
            location.calculer_paiements(montant_paye_caisse)
            location.save()

            # Calculer le prix total final
            prix_total = location.montant_total_facture
            detail_paiement = location.get_detail_paiement()

            # Construire le message selon le statut de paiement
            message_base = (
                f"Location de bloc créée avec succès pour le {date_operation.strftime('%d/%m/%Y')}. "
                f"Prix total: {prix_total:.2f} DA"
            )

            if location.statut_paiement == "EQUILIBRE":
                message_paiement = (
                    f" - Paiement équilibré ({montant_paye_caisse:.2f} DA)"
                )
            elif location.statut_paiement == "SURPLUS_CLINIQUE":
                message_paiement = f" - Surplus de {location.surplus_a_verser:.2f} DA à verser au médecin"
            elif location.statut_paiement == "COMPLEMENT_MEDECIN":
                message_paiement = f" - Complément de {location.complement_du_medecin:.2f} DA dû par le médecin"
            elif location.statut_paiement == "AUCUN_PAIEMENT":
                message_paiement = " - Aucun paiement enregistré"
            else:
                message_paiement = ""

            messages.success(request, message_base + message_paiement)

            return redirect("medical:location_bloc_detail", location_id=location.id)

        except Exception as e:
            logger.exception("Erreur lors de la création de la location")
            errors.append(f"Erreur lors de la création : {str(e)}")
            return self._render_with_errors(request, errors)


@login_required
def get_all_blocs_data(request):
    """Retourne tous les blocs avec leurs produits inclus pour le JavaScript"""
    try:
        blocs_data = {}
        for bloc in Bloc.objects.filter(est_actif=True).prefetch_related(
            "produits_inclus__produit"
        ):
            blocs_data[str(bloc.id)] = {
                "id": bloc.id,
                "nom_bloc": bloc.nom_bloc,
                "prix_base": float(bloc.prix_base),
                "prix_supplement_30min": float(bloc.prix_supplement_30min),
                "produits_inclus": [
                    {
                        "id": bp.produit.id,
                        "nom": bp.produit.nom,
                        "quantite_defaut": bp.quantite,
                        "prix_unitaire": float(bp.produit.prix_vente),
                    }
                    for bp in bloc.produits_inclus.all()
                ],
            }

        return JsonResponse({"success": True, "blocs": blocs_data})

    except Exception as e:
        logger.exception("Erreur lors de la récupération des données des blocs")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_all_forfaits_data(request):
    """Retourne tous les forfaits avec leurs produits ET actes inclus pour le JavaScript"""
    try:
        forfaits_data = {}
        for forfait in Forfait.objects.filter(est_actif=True).prefetch_related(
            "produits__produit", "actes_inclus__acte"  # NOUVEAU
        ):
            forfaits_data[str(forfait.id)] = {
                "id": forfait.id,
                "nom": forfait.nom,
                "prix": float(forfait.prix),
                "duree": forfait.duree,
                "produits_inclus": [
                    {
                        "id": fp.produit.id,
                        "nom": fp.produit.nom,
                        "quantite_defaut": fp.quantite,
                        "prix_unitaire": float(fp.produit.prix_vente),
                    }
                    for fp in forfait.produits.all()
                ],
                # NOUVEAU : Actes inclus dans le forfait
                "actes_inclus": [
                    {
                        "id": fa.acte.id,
                        "nom": fa.acte.nom,
                        "quantite_incluse": fa.quantite,
                        "prix_unitaire_inclus": float(fa.prix_unitaire_inclus),
                        "prix_standard": float(fa.acte.prix),
                        "duree_estimee": fa.acte.duree_estimee,
                    }
                    for fa in forfait.actes_inclus.all()
                ],
            }

        return JsonResponse({"success": True, "forfaits": forfaits_data})

    except Exception as e:
        logger.exception("Erreur lors de la récupération des données des forfaits")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_all_actes_data(request):
    """Retourne tous les actes avec leurs produits inclus pour le JavaScript"""
    try:
        actes_data = []
        for acte in ActeLocation.objects.filter(est_actif=True).prefetch_related(
            "produits_inclus__produit"
        ):
            actes_data.append(
                {
                    "id": acte.id,
                    "nom": acte.nom,
                    "prix": float(acte.prix),
                    "duree_estimee": acte.duree_estimee,
                    "produits_inclus": [
                        {
                            "id": ap.produit.id,
                            "nom": ap.produit.nom,
                            "quantite_defaut": ap.quantite_standard,
                            "prix_unitaire": float(ap.produit.prix_vente),
                            "est_obligatoire": ap.est_obligatoire,
                        }
                        for ap in acte.produits_inclus.all()
                    ],
                }
            )

        return JsonResponse({"success": True, "actes": actes_data})

    except Exception as e:
        logger.exception("Erreur lors de la récupération des données des actes")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_produits_supplementaires(request):
    """Retourne la liste des produits disponibles pour les suppléments"""
    try:
        produits = []
        for produit in Produit.objects.filter(est_actif=True).order_by("nom"):
            produits.append(
                {
                    "id": produit.id,
                    "nom": produit.nom,
                    "code": produit.code_produit or "",
                    "prix": float(produit.prix_vente),
                }
            )

        return JsonResponse({"success": True, "produits": produits})

    except Exception as e:
        logger.exception("Erreur lors de la récupération des produits supplémentaires")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# VUES AJAX SPÉCIFIQUES (gardées pour compatibilité et usage ciblé)


@login_required
def get_bloc_produits(request, bloc_id):
    """Retourne les produits inclus dans un bloc avec leurs quantités par défaut"""
    try:
        bloc = get_object_or_404(Bloc, id=bloc_id)
        produits = []

        for bloc_produit in bloc.produits_inclus.all():
            produits.append(
                {
                    "id": bloc_produit.produit.id,
                    "nom": bloc_produit.produit.nom,
                    "code_produit": bloc_produit.produit.code_produit or "",
                    "quantite_defaut": bloc_produit.quantite,
                    "prix_vente": float(bloc_produit.produit.prix_vente),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "bloc": {
                    "id": bloc.id,
                    "nom_bloc": bloc.nom_bloc,
                    "prix_base": float(bloc.prix_base),
                    "prix_supplement_30min": float(bloc.prix_supplement_30min),
                },
                "produits": produits,
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des produits du bloc {bloc_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_forfait_produits(request, forfait_id):
    """Retourne les produits ET actes inclus dans un forfait"""
    try:
        forfait = get_object_or_404(Forfait, id=forfait_id)
        produits = []
        actes = []  # NOUVEAU

        for forfait_produit in forfait.produits.all():
            produits.append(
                {
                    "id": forfait_produit.produit.id,
                    "nom": forfait_produit.produit.nom,
                    "code_produit": forfait_produit.produit.code_produit or "",
                    "quantite_defaut": forfait_produit.quantite,
                    "prix_vente": float(forfait_produit.produit.prix_vente),
                }
            )

        # NOUVEAU : Actes inclus dans le forfait
        for forfait_acte in forfait.actes_inclus.all():
            actes.append(
                {
                    "id": forfait_acte.acte.id,
                    "nom": forfait_acte.acte.nom,
                    "quantite_incluse": forfait_acte.quantite,
                    "prix_unitaire_inclus": float(forfait_acte.prix_unitaire_inclus),
                    "prix_standard": float(forfait_acte.acte.prix),
                    "duree_estimee": forfait_acte.acte.duree_estimee,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "forfait": {
                    "id": forfait.id,
                    "nom": forfait.nom,
                    "prix": float(forfait.prix),
                    "duree": forfait.duree,
                },
                "produits": produits,
                "actes": actes,  # NOUVEAU
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des données du forfait {forfait_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# NOUVELLE FONCTION : Calculer les écarts d'actes pour un forfait
@login_required
def get_forfait_actes_ecarts(request, location_id):
    """Retourne les écarts entre actes inclus et actes utilisés pour une location forfaitaire"""
    try:
        location = get_object_or_404(LocationBloc, id=location_id)

        if location.type_tarification != "FORFAIT" or not location.forfait:
            return JsonResponse({"success": False, "error": "Location non forfaitaire"})

        ecarts = location.get_ecarts_actes_forfait()

        return JsonResponse(
            {
                "success": True,
                "ecarts": ecarts,
                "montant_ecarts": float(location.montant_ecarts_actes_forfait),
                "economies": float(location.economies_actes_forfait),
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors du calcul des écarts d'actes pour la location {location_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_acte_produits(request, acte_id):
    """Retourne les produits inclus dans un acte avec leurs quantités par défaut"""
    try:
        acte = get_object_or_404(ActeLocation, id=acte_id)
        produits = []

        for acte_produit in acte.produits_inclus.all():
            produits.append(
                {
                    "id": acte_produit.produit.id,
                    "nom": acte_produit.produit.nom,
                    "code_produit": acte_produit.produit.code_produit or "",
                    "quantite_defaut": acte_produit.quantite_standard,
                    "prix_vente": float(acte_produit.produit.prix_vente),
                    "est_obligatoire": acte_produit.est_obligatoire,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "acte": {
                    "id": acte.id,
                    "nom": acte.nom,
                    "prix": float(acte.prix),
                    "duree_estimee": acte.duree_estimee,
                },
                "produits": produits,
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des produits de l'acte {acte_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


class ForfaitDetailView(View):
    """API pour récupérer les détails d'un forfait avec produits inclus"""

    def get(self, request, forfait_id):
        try:
            forfait = get_object_or_404(Forfait, id=forfait_id)

            data = {
                "id": forfait.id,
                "nom": forfait.nom,
                "description": forfait.description,
                "prix": float(forfait.prix),
                "duree": forfait.duree,
                "produits": [
                    {
                        "id": fp.produit.id,
                        "nom": fp.produit.nom,
                        "code": fp.produit.code_produit,
                        "quantite": fp.quantite,
                        "prix_unitaire": float(fp.produit.prix_vente),
                        "prix_total": float(fp.quantite * fp.produit.prix_vente),
                    }
                    for fp in forfait.produits.all()
                ],
            }

            return JsonResponse(data)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class ActeDetailView(View):
    """API pour récupérer les détails d'un acte avec produits inclus"""

    def get(self, request, acte_id):
        try:
            acte = get_object_or_404(ActeLocation, id=acte_id)

            data = {
                "id": acte.id,
                "nom": acte.nom,
                "description": acte.description,
                "prix": float(acte.prix),
                "duree_estimee": acte.duree_estimee,
                "produits_obligatoires": [
                    {
                        "id": ap.produit.id,
                        "nom": ap.produit.nom,
                        "code": ap.produit.code_produit,
                        "quantite_standard": ap.quantite_standard,
                        "prix_unitaire": float(ap.produit.prix_vente),
                        "est_obligatoire": ap.est_obligatoire,
                    }
                    for ap in ActeProduitInclus.objects.filter(acte=acte)
                ],
            }

            return JsonResponse(data)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
