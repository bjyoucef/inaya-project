# medical/views/bloc_location.py

import io
import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
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
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from medecin.models import Medecin
from medical.models import PrestationKt
from medical.models.bloc_location import (ActeLocation, ActeProduitInclus,
                                          Bloc, BlocProduitInclus,
                                          ConsommationProduitBloc, Forfait,
                                          ForfaitActeInclus,
                                          ForfaitProduitInclus, LocationBloc,
                                          LocationBlocActe)
from patients.models import Patient
from pharmacies.models import Produit
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

logger = logging.getLogger(__name__)


class LocationBlocCreateView(View):
    """Création d'une location de bloc avec gestion automatique des produits inclus"""

    def get(self, request):
        context = {
            "patients": Patient.objects.all(),
            "medecins": Medecin.objects.all(),
            "blocs": Bloc.objects.filter(est_actif=True).order_by("nom_bloc"),
            "forfaits": Forfait.objects.filter(est_actif=True).order_by("nom"),
            "actes_location": ActeLocation.objects.filter(est_actif=True).order_by("nom"),
            "now": timezone.localdate(),
        }
        return render(request, "locations/location_create.html", context)

    def _render_with_errors(self, request, errors):
        context = {
            "patients": Patient.objects.all(),
            "medecins": Medecin.objects.all(),
            "blocs": Bloc.objects.filter(est_actif=True).order_by("nom_bloc"),
            "forfaits": Forfait.objects.filter(est_actif=True).order_by("nom"),
            "actes_location": ActeLocation.objects.filter(est_actif=True).order_by("nom"),
            "now": timezone.localdate(),
                "errors": errors,
                "form_data": request.POST,
            }
        return render(request, "locations/location_create.html", context)

    @transaction.atomic
    def post(self, request):
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

        # GESTION DES PAIEMENTS
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
            errors.append("Le nom de l'intervention est obligatoire pour la tarification à la durée.")

        # Validation du forfait si tarification forfaitaire
        forfait_id = request.POST.get("forfait") if type_tarification == "FORFAIT" else None
        if type_tarification == "FORFAIT" and not forfait_id:
            errors.append("Un forfait doit être sélectionné pour la tarification forfaitaire.")

        duree_reelle = None
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

        date_operation = parse_date(date_operation_str)
        if date_operation is None:
            errors.append("Format de date invalide (YYYY-MM-DD).")

        # Traitement des heures (optionnelles)

        heure_operation = None
        if heure_operation_str:
            try:
                heure_operation = datetime.strptime(heure_operation_str, "%H:%M").time()
            except Exception:
                errors.append("Format heure invalide (HH:MM).")

        # ========== RÉCUPÉRATION DES DONNÉES DU FORMULAIRE ==========

        # 1. Actes inclus dans le forfait (NOUVEAU)
        actes_inclus_data = {}
        if type_tarification == "FORFAIT":
            actes_inclus_ids = request.POST.getlist("actes_inclus[id][]") or []
            quantites_utilisees_actes = request.POST.getlist("actes_inclus[quantite_utilisee][]") or []

            for i, acte_id in enumerate(actes_inclus_ids):
                if acte_id:
                    try:
                        quantite_utilisee = int(quantites_utilisees_actes[i]) if i < len(quantites_utilisees_actes) else 0
                        actes_inclus_data[int(acte_id)] = quantite_utilisee
                    except (ValueError, IndexError):
                        pass

        # 2. Produits des actes forfaitaires (NOUVEAU)
        produits_actes_forfait_data = {}
        if type_tarification == "FORFAIT":
            # Parcourir tous les index possibles pour les actes forfaitaires
            for acte_idx in range(20):  # Limiter à 20 actes max
                for prod_idx in range(50):  # Limiter à 50 produits par acte max
                    prod_id_key = f"actes_forfait[{acte_idx}][produits][{prod_idx}][id]"
                    qte_key = f"actes_forfait[{acte_idx}][produits][{prod_idx}][quantite_utilisee]"

                    prod_id = request.POST.get(prod_id_key)
                    qte_utilisee = request.POST.get(qte_key)

                    if prod_id and qte_utilisee:
                        try:
                            acte_id_from_form = request.POST.get(f"actes_forfait[{acte_idx}][acte_id]")
                            if acte_id_from_form:
                                key = f"{acte_id_from_form}_{prod_id}"
                                produits_actes_forfait_data[key] = float(qte_utilisee)
                        except (ValueError, KeyError):
                            continue

        # 3. Produits inclus (bloc/forfait) avec quantités réelles ajustées
        produits_inclus_data = []
        produit_inclus_ids = request.POST.getlist("produits_inclus[id][]") or []
        quantites_reelles_inclus = request.POST.getlist("produits_inclus[quantite_reelle][]") or []

        for i, produit_id in enumerate(produit_inclus_ids):
            if not produit_id:
                continue
            try:
                quantite_reelle = (
                    float(quantites_reelles_inclus[i])
                    if i < len(quantites_reelles_inclus) and quantites_reelles_inclus[i]
                    else 0
                )
                if quantite_reelle >= 0:
                    produits_inclus_data.append({
                        "produit_id": produit_id,
                        "quantite_reelle": quantite_reelle
                    })
            except (ValueError, IndexError):
                errors.append(f"Données invalides pour le produit inclus {i+1}")

        # 4. Actes supplémentaires avec leurs produits
        actes_data = []
        acte_ids = request.POST.getlist("acte_id[]")
        acte_quantites = request.POST.getlist("acte_quantite[]")
        acte_prix = request.POST.getlist("acte_prix[]")

        for i, acte_id in enumerate(acte_ids):
            if not acte_id:
                continue
            try:
                quantite = int(acte_quantites[i]) if i < len(acte_quantites) and acte_quantites[i] else 1
                prix = Decimal(acte_prix[i]) if i < len(acte_prix) and acte_prix[i] else None

                if quantite > 0:
                    # Récupérer les produits de cet acte
                    acte_produits = []
                    produit_acte_ids = request.POST.getlist(f"actes[{i}][produits][]") or []
                    quantites_acte_produits = request.POST.getlist(f"actes[{i}][quantites_reelles][]") or []

                    for j, prod_id in enumerate(produit_acte_ids):
                        if prod_id:
                            try:
                                qte_reelle = float(quantites_acte_produits[j]) if j < len(quantites_acte_produits) else 0
                                acte_produits.append({
                                        "produit_id": prod_id,
                                        "quantite_reelle": qte_reelle,
                                })
                            except (ValueError, IndexError):
                                continue

                    actes_data.append({
                            "acte_id": acte_id,
                            "quantite": quantite,
                            "prix": prix,
                            "produits": acte_produits,
                    })
            except (ValueError, IndexError):
                errors.append(f"Données invalides pour l'acte {i+1}")

        # 5. Produits supplémentaires
        produits_supp = []
        produits_supp_ids = request.POST.getlist("produits_supp[id][]") or []
        quantites_supp = request.POST.getlist("produits_supp[quantite][]") or []
        prix_supp = request.POST.getlist("produits_supp[prix][]") or []

        for i, pid in enumerate(produits_supp_ids):
            if not pid:
                continue
            try:
                q = float(quantites_supp[i]) if i < len(quantites_supp) and quantites_supp[i] else 1
                p = float(prix_supp[i]) if i < len(prix_supp) and prix_supp[i] else 0
                if q > 0:
                    produits_supp.append({
                        "produit_id": pid,
                        "quantite": q,
                        "prix_unitaire": p
                    })
            except ValueError:
                errors.append(f"Quantité ou prix invalide pour le produit supplémentaire {i+1}")

        # Si erreurs, retourner au formulaire
        if errors:
            return self._render_with_errors(request, errors)

        # ========== CRÉATION DE LA LOCATION ==========
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
                montant_paye_caisse=montant_paye_caisse,
                notes_paiement=notes_paiement,
            )
            location.save()

            # ========== GESTION DES ACTES ET PRODUITS INCLUS DANS LE FORFAIT ==========
            if type_tarification == "FORFAIT" and forfait:
                actes_inclus_forfait = ForfaitActeInclus.objects.filter(forfait=forfait).select_related('acte').prefetch_related('acte__produits_inclus__produit')

                for acte_inclus in actes_inclus_forfait:
                    # Déterminer la quantité utilisée (depuis le formulaire ou par défaut)
                    quantite_utilisee = actes_inclus_data.get(acte_inclus.acte.id, acte_inclus.quantite)

                    # Créer l'association acte-location pour la partie incluse
                    location_acte_inclus = LocationBlocActe.objects.create(
                        location=location,
                        acte=acte_inclus.acte,
                        quantite=min(quantite_utilisee, acte_inclus.quantite),
                        prix_unitaire=acte_inclus.prix_unitaire_inclus,
                    )

                    # Si quantité utilisée > quantité incluse, créer un acte supplémentaire
                    if quantite_utilisee > acte_inclus.quantite:
                        quantite_supplementaire = quantite_utilisee - acte_inclus.quantite
                    LocationBlocActe.objects.create(
                        location=location,
                        acte=acte_inclus.acte,
                            quantite=quantite_supplementaire,
                            prix_unitaire=acte_inclus.acte.prix,
                    )

                    # Ajouter les produits inclus dans ces actes
                    for acte_produit_inclus in acte_inclus.acte.produits_inclus.all():
                        # Calculer les quantités
                        quantite_par_acte = acte_produit_inclus.quantite_standard
                        quantite_totale_incluse = quantite_par_acte * acte_inclus.quantite
                        quantite_totale_utilisee = quantite_par_acte * quantite_utilisee

                        # Vérifier si une quantité spécifique a été saisie pour ce produit
                        cle_produit = f"{acte_inclus.acte.id}_{acte_produit_inclus.produit.id}"
                        if cle_produit in produits_actes_forfait_data:
                            quantite_totale_utilisee = produits_actes_forfait_data[cle_produit]

                        # Vérifier si une consommation existe déjà pour ce produit
                        consommation_existante = ConsommationProduitBloc.objects.filter(
                            location=location,
                            produit=acte_produit_inclus.produit,
                        ).first()

                        if consommation_existante:
                            # Mettre à jour la consommation existante
                            consommation_existante.quantite += quantite_totale_utilisee
                            consommation_existante.quantite_incluse += quantite_totale_incluse
                            consommation_existante.ecart_quantite = (
                                    consommation_existante.quantite - consommation_existante.quantite_incluse
                            )
                            consommation_existante.est_inclus = (consommation_existante.ecart_quantite <= 0)

                            # Mise à jour de la source
                            if consommation_existante.source_inclusion == "FORFAIT":
                                consommation_existante.source_inclusion = "FORFAIT_MIXTE"
                            elif consommation_existante.source_inclusion not in ["FORFAIT_ACTE", "FORFAIT_MIXTE"]:
                                consommation_existante.source_inclusion = "FORFAIT_MIXTE"

                            consommation_existante.save()
                        else:
                            # Créer une nouvelle consommation
                            if quantite_totale_utilisee > 0:
                                ecart = quantite_totale_utilisee - quantite_totale_incluse
                            ConsommationProduitBloc.objects.create(
                                location=location,
                                produit=acte_produit_inclus.produit,
                                    quantite=quantite_totale_utilisee,
                                prix_unitaire=Decimal(acte_produit_inclus.produit.prix_vente),
                                    est_inclus=(ecart <= 0),
                                    source_inclusion="FORFAIT_ACTE",
                                    quantite_incluse=quantite_totale_incluse,
                                    ecart_quantite=ecart,
                                    acte_associe=location_acte_inclus,
                            )

            # ========== GESTION DES PRODUITS INCLUS AVEC QUANTITÉS RÉELLES ==========

            # 1. Produits inclus dans le bloc (DUREE)
            if type_tarification == "DUREE":
                quantites_reelles_dict = {
                    int(p["produit_id"]): p["quantite_reelle"]
                    for p in produits_inclus_data
                }

                for bloc_produit in BlocProduitInclus.objects.filter(bloc=bloc):
                    quantite_reelle = quantites_reelles_dict.get(
                        bloc_produit.produit.id,
                        bloc_produit.quantite,
                    )

                    ecart = quantite_reelle - bloc_produit.quantite

                    if quantite_reelle > 0:
                        ConsommationProduitBloc.objects.create(
                            location=location,
                            produit=bloc_produit.produit,
                            quantite=quantite_reelle,
                            prix_unitaire=Decimal(bloc_produit.produit.prix_vente),
                            est_inclus=(ecart <= 0),
                            source_inclusion="BLOC",
                            quantite_incluse=bloc_produit.quantite,
                            ecart_quantite=ecart,
                        )

            # 2. Produits inclus directement dans le forfait (FORFAIT)
            if type_tarification == "FORFAIT" and forfait:
                quantites_reelles_dict = {
                    int(p["produit_id"]): p["quantite_reelle"]
                    for p in produits_inclus_data
                }

                for forfait_produit in forfait.produits.all():
                    quantite_reelle = quantites_reelles_dict.get(
                        forfait_produit.produit.id,
                        forfait_produit.quantite,
                    )

                    ecart = quantite_reelle - forfait_produit.quantite

                    # Vérifier si ce produit existe déjà (via les actes inclus)
                    consommation_existante = ConsommationProduitBloc.objects.filter(
                        location=location,
                        produit=forfait_produit.produit,
                    ).first()

                    if consommation_existante:
                        # Mettre à jour avec la quantité réelle et ajouter à l'inclusion
                        consommation_existante.quantite = max(consommation_existante.quantite, quantite_reelle)
                        consommation_existante.quantite_incluse += forfait_produit.quantite
                        consommation_existante.ecart_quantite = (
                            consommation_existante.quantite - consommation_existante.quantite_incluse
                        )
                        consommation_existante.est_inclus = (consommation_existante.ecart_quantite <= 0)

                        # Mise à jour de la source
                        if consommation_existante.source_inclusion == "FORFAIT_ACTE":
                            consommation_existante.source_inclusion = "FORFAIT_MIXTE"
                        elif consommation_existante.source_inclusion not in ["FORFAIT", "FORFAIT_MIXTE"]:
                            consommation_existante.source_inclusion = "FORFAIT_MIXTE"

                        consommation_existante.save()
                    else:
                        # Créer nouvelle consommation pour les produits directement inclus dans le forfait
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

            # ========== GESTION DES ACTES SUPPLÉMENTAIRES ==========
            for acte_data in actes_data:
                try:
                    acte = ActeLocation.objects.get(id=acte_data["acte_id"])
                    prix_unitaire = acte_data["prix"] if acte_data["prix"] else acte.prix

                    # Vérifier si cet acte est déjà inclus dans le forfait
                    if type_tarification == "FORFAIT" and forfait:
                        acte_inclus = ForfaitActeInclus.objects.filter(
                            forfait=forfait, acte=acte
                        ).first()

                        if acte_inclus:
                            # Cet acte est partiellement ou totalement inclus
                            quantite_supplementaire = max(0, acte_data["quantite"] - acte_inclus.quantite)
                            if quantite_supplementaire > 0:
                                # Créer seulement pour la partie supplémentaire
                                location_acte = LocationBlocActe.objects.create(
                                    location=location,
                                    acte=acte,
                                    quantite=quantite_supplementaire,
                                    prix_unitaire=prix_unitaire,
                                )
                            # Les produits de la partie incluse sont déjà gérés plus haut
                            continue

                        # Créer l'association acte-location (acte entièrement supplémentaire)
                        location_acte = LocationBlocActe.objects.create(
                            location=location,
                            acte=acte,
                            quantite=acte_data["quantite"],
                            prix_unitaire=prix_unitaire,
                        )

                    # Ajouter les produits de l'acte avec quantités réelles
                    for prod_acte_data in acte_data["produits"]:
                        try:
                            produit = Produit.objects.get(id=prod_acte_data["produit_id"])
                            quantite_reelle = prod_acte_data["quantite_reelle"]

                            # Vérifier si c'est un produit inclus dans l'acte
                            try:
                                acte_produit_inclus = ActeProduitInclus.objects.get(
                                    acte=acte, produit=produit
                                )
                                # Quantité incluse = quantité standard * nombre d'actes
                                quantite_incluse = acte_produit_inclus.quantite_standard * acte_data["quantite"]
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
                                    prix_unitaire=Decimal(produit.prix_vente),
                                    est_inclus=est_inclus,
                                    source_inclusion=source,
                                    quantite_incluse=quantite_incluse,
                                    ecart_quantite=ecart,
                                    acte_associe=location_acte,
                                )

                        except Produit.DoesNotExist:
                            logger.error(f"Produit d'acte introuvable: {prod_acte_data['produit_id']}")
                            continue

                except ActeLocation.DoesNotExist:
                    logger.error(f"Acte introuvable: {acte_data['acte_id']}")
                    continue

            # ========== GESTION DES PRODUITS SUPPLÉMENTAIRES ==========
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
                        ecart_quantite=ps["quantite"],
                    )
                except Produit.DoesNotExist:
                    logger.error(f"Produit supplémentaire introuvable: {ps['produit_id']}")
                    continue

            # ========== CALCULS FINAUX ET PAIEMENTS ==========
            location.calculer_paiements(montant_paye_caisse)
            location.save()

            # Message de succès avec détails du paiement
            prix_total = location.montant_total_facture
            message_base = (
                f"Location de bloc créée avec succès pour le {date_operation.strftime('%d/%m/%Y')}. "
                f"Prix total: {prix_total:.2f} DA"
            )

            if location.statut_paiement == "EQUILIBRE":
                message_paiement = f" - Paiement équilibré ({montant_paye_caisse:.2f} DA)"
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


# ========== VUES AJAX POUR LE CHARGEMENT DES DONNÉES ==========

@login_required
def get_all_blocs_data(request):
    """Retourne tous les blocs avec leurs produits inclus pour le JavaScript"""
    try:
        blocs_data = {}
        for bloc in Bloc.objects.filter(est_actif=True).prefetch_related("produits_inclus__produit"):
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
            "produits__produit",
            "actes_inclus__acte__produits_inclus__produit"
        ):
            # Récupérer les actes inclus avec leurs produits
            actes_inclus = []
            for fa in forfait.actes_inclus.all():
                actes_inclus.append({
                    "id": fa.acte.id,
                    "nom": fa.acte.nom,
                    "quantite_incluse": fa.quantite,
                    "prix_unitaire_inclus": float(fa.prix_unitaire_inclus),
                    "prix_standard": float(fa.acte.prix),
                    "duree_estimee": fa.acte.duree_estimee,
                    "produits_inclus": [
                        {
                            "id": ap.produit.id,
                            "nom": ap.produit.nom,
                            "quantite_defaut": ap.quantite_standard,
                            "prix_unitaire": float(ap.produit.prix_vente),
                        }
                        for ap in fa.acte.produits_inclus.all()
                    ],
                })

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
                "actes_inclus": actes_inclus,
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
        for acte in ActeLocation.objects.filter(est_actif=True).prefetch_related("produits_inclus__produit"):
            actes_data.append({
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
            })

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
            produits.append({
                    "id": produit.id,
                    "nom": produit.nom,
                    "code": produit.code_produit or "",
                    "prix": float(produit.prix_vente),
            })

        return JsonResponse({"success": True, "produits": produits})

    except Exception as e:
        logger.exception("Erreur lors de la récupération des produits supplémentaires")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# ========== VUES AJAX SPÉCIFIQUES ==========

@login_required
def get_bloc_produits(request, bloc_id):
    """Retourne les produits inclus dans un bloc avec leurs quantités par défaut"""
    try:
        bloc = get_object_or_404(Bloc, id=bloc_id)
        produits = []

        for bloc_produit in bloc.produits_inclus.all():
            produits.append({
                    "id": bloc_produit.produit.id,
                    "nom": bloc_produit.produit.nom,
                    "code_produit": bloc_produit.produit.code_produit or "",
                    "quantite_defaut": bloc_produit.quantite,
                    "prix_vente": float(bloc_produit.produit.prix_vente),
            })

        return JsonResponse({
                "success": True,
                "bloc": {
                    "id": bloc.id,
                    "nom_bloc": bloc.nom_bloc,
                    "prix_base": float(bloc.prix_base),
                    "prix_supplement_30min": float(bloc.prix_supplement_30min),
                },
                "produits": produits,
        })

    except Exception as e:
        logger.exception(f"Erreur lors de la récupération des produits du bloc {bloc_id}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_forfait_produits(request, forfait_id):
    """Retourne les produits ET actes inclus dans un forfait"""
    try:
        forfait = get_object_or_404(Forfait, id=forfait_id)
        produits = []
        actes = []

        for forfait_produit in forfait.produits.all():
            produits.append({
                    "id": forfait_produit.produit.id,
                    "nom": forfait_produit.produit.nom,
                    "code_produit": forfait_produit.produit.code_produit or "",
                    "quantite_defaut": forfait_produit.quantite,
                    "prix_vente": float(forfait_produit.produit.prix_vente),
            })

        # Actes inclus dans le forfait avec leurs produits
        for forfait_acte in forfait.actes_inclus.all():
            acte_data = {
                    "id": forfait_acte.acte.id,
                    "nom": forfait_acte.acte.nom,
                    "quantite_incluse": forfait_acte.quantite,
                    "prix_unitaire_inclus": float(forfait_acte.prix_unitaire_inclus),
                    "prix_standard": float(forfait_acte.acte.prix),
                    "duree_estimee": forfait_acte.acte.duree_estimee,
                "produits_inclus": []
                }

            # Ajouter les produits de cet acte
            for acte_produit in forfait_acte.acte.produits_inclus.all():
                acte_data["produits_inclus"].append({
                    "id": acte_produit.produit.id,
                    "nom": acte_produit.produit.nom,
                    "quantite_defaut": acte_produit.quantite_standard,
                    "prix_unitaire": float(acte_produit.produit.prix_vente),
                })

            actes.append(acte_data)

        return JsonResponse({
                "success": True,
                "forfait": {
                    "id": forfait.id,
                    "nom": forfait.nom,
                    "prix": float(forfait.prix),
                    "duree": forfait.duree,
                },
                "produits": produits,
            "actes": actes,
        })

    except Exception as e:
        logger.exception(f"Erreur lors de la récupération des données du forfait {forfait_id}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_acte_produits(request, acte_id):
    """Retourne les produits inclus dans un acte avec leurs quantités par défaut"""
    try:
        acte = get_object_or_404(ActeLocation, id=acte_id)
        produits = []

        for acte_produit in acte.produits_inclus.all():
            produits.append({
                    "id": acte_produit.produit.id,
                    "nom": acte_produit.produit.nom,
                    "code_produit": acte_produit.produit.code_produit or "",
                    "quantite_defaut": acte_produit.quantite_standard,
                    "prix_vente": float(acte_produit.produit.prix_vente),
                    "est_obligatoire": acte_produit.est_obligatoire,
            })

        return JsonResponse({
                "success": True,
                "acte": {
                    "id": acte.id,
                    "nom": acte.nom,
                    "prix": float(acte.prix),
                    "duree_estimee": acte.duree_estimee,
                },
                "produits": produits,
        })

    except Exception as e:
        logger.exception(f"Erreur lors de la récupération des produits de l'acte {acte_id}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@login_required
def get_forfait_actes_ecarts(request, location_id):
    """Retourne les écarts entre actes inclus et actes utilisés pour une location forfaitaire"""
    try:
        location = get_object_or_404(LocationBloc, id=location_id)

        if location.type_tarification != "FORFAIT" or not location.forfait:
            return JsonResponse({"success": False, "error": "Location non forfaitaire"})

        ecarts = location.get_ecarts_actes_forfait()

        return JsonResponse({
            "success": True,
            "ecarts": ecarts,
            "montant_ecarts": float(location.montant_ecarts_actes_forfait),
            "economies": float(location.economies_actes_forfait),
        })

    except Exception as e:
        logger.exception(f"Erreur lors du calcul des écarts d'actes pour la location {location_id}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


class LocationBlocListView(ListView):
    model = LocationBloc
    template_name = "locations/location_bloc_list.html"
    context_object_name = "locations"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("bloc", "patient", "medecin", "forfait")
            .prefetch_related(
                Prefetch(
                    "consommations_produits",  # Fixed: was "consommations"
                    queryset=ConsommationProduitBloc.objects.select_related(
                        "produit", "acte_associe"
                    ),
                    to_attr="prefetched_consommations",
                )
            )
            .order_by("-date_operation")
        )

        # Filtres
        date_debut = self.request.GET.get("date_debut")
        date_fin = self.request.GET.get("date_fin")
        bloc_id = self.request.GET.get("bloc")
        medecin_id = self.request.GET.get("medecin")
        patient_id = self.request.GET.get("patient")

        if date_debut:
            queryset = queryset.filter(date_operation__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date_operation__lte=date_fin)
        if bloc_id:
            queryset = queryset.filter(bloc_id=bloc_id)
        if medecin_id:
            queryset = queryset.filter(medecin_id=medecin_id)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_obj = context["page_obj"]

        # Calcul des totaux pour la page courante
        total_prix_bloc = 0
        total_actes = 0
        total_produits_supp = 0
        total_page = 0

        for location in page_obj:
            total_prix_bloc += location.prix_final or 0
            total_actes += location.montant_total_actes
            total_produits_supp += location.montant_total_produits_supplementaires
            total_page += location.montant_total_facture

        # Ajout des totaux au contexte
        context.update(
            {
                "total_prix_bloc": total_prix_bloc,
                "total_actes": total_actes,
                "total_produits_supp": total_produits_supp,
                "total_page": total_page,
                "blocs": Bloc.objects.all(),
                "medecins": Medecin.objects.all(),
                "patients": Patient.objects.all(),
                "date_debut": self.request.GET.get("date_debut", ""),
                "date_fin": self.request.GET.get("date_fin", ""),
                "bloc_selected": self.request.GET.get("bloc", ""),
                "medecin_selected": self.request.GET.get("medecin", ""),
                "patient_selected": self.request.GET.get("patient", ""),
            }
        )

        return context


class LocationBlocDetailView(View):
    """
    Vue de détail pour une LocationBloc : charge proprement les consommations
    avec leur produit et l'acte associé pour éviter N+1 queries.
    """

    def get(self, request, location_id):
        # Charger les relations directes (bloc, patient, medecin, forfait) en select_related
        qs = LocationBloc.objects.select_related(
            "bloc", "patient", "medecin", "forfait"
        )

        # Précharger les consommations en optimisant les FK internes
        consommations_prefetch = Prefetch(
            "consommations_produits",  # Fixed: was "consommations"
            queryset=ConsommationProduitBloc.objects.select_related(
                "produit", "acte_associe"
            ),
            to_attr="prefetched_consommations",  # optionnel : éviter conflits et accès direct
        )

        qs = qs.prefetch_related(consommations_prefetch)

        location = get_object_or_404(qs, id=location_id)

        # Si vous avez choisi to_attr="prefetched_consommations", utilisez-le :
        consommations = getattr(location, "prefetched_consommations", None)
        # fallback si to_attr non utilisé :
        if consommations is None:
            consommations = location.consommations_produits.select_related(  # Fixed: was "consommations"
                "produit", "acte_associe"
            ).all()

        # Construire le résumé (vous avez déjà get_resume_consommation qui fait select_related,
        # mais ici on peut réutiliser consommations préchargées pour éviter de nouvelles requêtes)
        # Exemple simple: réutiliser la méthode existante si vous préférez
        resume = location.get_resume_consommation()

        context = {
            "location": location,
            "consommations": consommations,
            "resume_consommation": resume,
        }

        return render(request, "locations/location_detail.html", context)


class LocationBlocEditView(View):
    """Vue pour modifier une location de bloc existante"""

    def get(self, request, location_id):
        location = get_object_or_404(LocationBloc, id=location_id)
        context = {
            "location": location,
            "patients": Patient.objects.all(),
            "medecins": Medecin.objects.all(),
            "blocs": Bloc.objects.filter(est_actif=True).order_by("nom_bloc"),
            "forfaits": Forfait.objects.filter(est_actif=True)
            .prefetch_related("produits__produit")
            .order_by("nom"),
            "produits": Produit.objects.filter(est_actif=True).order_by("nom"),
            "actes_location": ActeLocation.objects.filter(est_actif=True)
            .prefetch_related("produits_inclus__produit")
            .order_by("nom"),
            "now": timezone.localdate(),
            "actes_selected": location.actes_location.all(),
            "produits_selected": location.consommations_produits.filter(
                est_inclus=False
            ),
        }
        return render(request, "locations/location_edit.html", context)

    @transaction.atomic
    def post(self, request, location_id):
        location = get_object_or_404(LocationBloc, id=location_id)
        errors = []

        # Récupération des champs
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        bloc_id = request.POST.get("bloc")
        nom_acte = request.POST.get("nom_acte", "").strip()
        type_tarification = request.POST.get("type_tarification", "DUREE")
        observations = request.POST.get("observations", "").strip()
        date_operation_str = request.POST.get("date_operation")
        heure_operation_str = request.POST.get("heure_operation", "")
        duree_reelle_str = request.POST.get("duree_reelle", "")
        forfait_id = (
            request.POST.get("forfait") if type_tarification == "FORFAIT" else None
        )

        # Validation des champs obligatoires
        if not all(
            [
                patient_id,
                medecin_id,
                bloc_id,
                date_operation_str,
                nom_acte,
                type_tarification,
            ]
        ):
            errors.append("Tous les champs obligatoires doivent être remplis.")

        if type_tarification == "FORFAIT" and not forfait_id:
            errors.append(
                "Un forfait doit être sélectionné pour la tarification forfaitaire."
            )

        duree_reelle = None
        if not duree_reelle_str:
            errors.append("La durée réelle est requise pour une opération.")
        else:
            try:
                duree_reelle = int(duree_reelle_str)
                if duree_reelle <= 0:
                    errors.append("La durée réelle doit être positive.")
            except ValueError:
                errors.append("Format de durée réelle invalide.")



        date_operation = parse_date(date_operation_str)
        if date_operation is None:
            errors.append("Format de date invalide (YYYY-MM-DD).")


        heure_operation = None
        if heure_operation_str:
            try:
                heure_operation = datetime.strptime(heure_operation_str, "%H:%M").time()
            except Exception:
                errors.append("Format heure invalide (HH:MM).")

        # Récupération des actes supplémentaires
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
                    actes_data.append(
                        {"acte_id": acte_id, "quantite": quantite, "prix": prix}
                    )
            except (ValueError, IndexError):
                errors.append(f"Données invalides pour l'acte {i+1}")

        # Récupération des produits supplémentaires
        produits_supp = []
        produit_ids = request.POST.getlist("produit_id[]")
        quantites = request.POST.getlist("quantite[]")
        for i, pid in enumerate(produit_ids):
            if not pid:
                continue
            try:
                q = int(quantites[i]) if i < len(quantites) and quantites[i] else 1
                if q > 0:
                    produits_supp.append({"produit_id": pid, "quantite": q})
            except ValueError:
                errors.append(f"Quantité invalide pour le produit {i+1}")

        if errors:
            return self._render_with_errors(request, location_id, errors)

        try:
            patient = get_object_or_404(Patient, id=patient_id)
            medecin = get_object_or_404(Medecin, id=medecin_id)
            bloc = get_object_or_404(Bloc, id=bloc_id)
            forfait = get_object_or_404(Forfait, id=forfait_id) if forfait_id else None

            # Mise à jour de la location
            location.patient = patient
            location.medecin = medecin
            location.bloc = bloc
            location.date_operation = date_operation
            location.heure_operation = heure_operation
            location.nom_acte = nom_acte
            location.type_tarification = type_tarification
            location.forfait = forfait
            location.duree_reelle = duree_reelle
            location.observations = observations
            location.modifie_par = request.user

            # Supprimer les actes et produits existants
            location.actes_location.all().delete()
            location.consommations_produits.all().delete()

            # Enregistrer la location
            location.save()

            # Ajouter les produits inclus dans le bloc
            if type_tarification == "DUREE":
                for bloc_produit in BlocProduitInclus.objects.filter(bloc=bloc):
                    ConsommationProduitBloc.objects.create(
                        location=location,
                        produit=bloc_produit.produit,
                        quantite=bloc_produit.quantite,
                        prix_unitaire=Decimal(bloc_produit.produit.prix_vente),
                        est_inclus=True,
                        source_inclusion="BLOC",
                    )

            # Ajouter les produits inclus dans le forfait
            if type_tarification == "FORFAIT" and forfait:
                for forfait_produit in forfait.produits.all():
                    ConsommationProduitBloc.objects.create(
                        location=location,
                        produit=forfait_produit.produit,
                        quantite=forfait_produit.quantite,
                        prix_unitaire=Decimal(forfait_produit.produit.prix_vente),
                        est_inclus=True,
                        source_inclusion="FORFAIT",
                    )

            # Ajouter les actes supplémentaires
            montant_total_actes = Decimal(0)
            for acte_data in actes_data:
                try:
                    acte = ActeLocation.objects.get(id=acte_data["acte_id"])
                    prix_unitaire = (
                        acte_data["prix"] if acte_data["prix"] else acte.prix
                    )
                    location_acte = LocationBlocActe.objects.create(
                        location=location,
                        acte=acte,
                        quantite=acte_data["quantite"],
                        prix_unitaire=prix_unitaire,
                    )
                    montant_total_actes += location_acte.prix_total

                    # Ajouter les produits obligatoires de l'acte
                    for produit_acte in ActeProduitInclus.objects.filter(
                        acte=acte, est_obligatoire=True
                    ):
                        quantite_totale = (
                            produit_acte.quantite_standard * acte_data["quantite"]
                        )
                        ConsommationProduitBloc.objects.create(
                            location=location,
                            produit=produit_acte.produit,
                            quantite=quantite_totale,
                            prix_unitaire=Decimal(produit_acte.produit.prix_vente),
                            est_inclus=True,
                            source_inclusion="ACTE",
                        )
                except ActeLocation.DoesNotExist:
                    continue

            # Ajouter les produits supplémentaires
            for ps in produits_supp:
                try:
                    prod = Produit.objects.get(id=ps["produit_id"])
                    ConsommationProduitBloc.objects.create(
                        location=location,
                        produit=prod,
                        quantite=ps["quantite"],
                        prix_unitaire=Decimal(prod.prix_vente),
                        est_inclus=False,
                        source_inclusion="SUPPLEMENTAIRE",
                    )
                except Produit.DoesNotExist:
                    continue

            messages.success(
                request,
                f"Location de bloc '{location.nom_acte}' modifiée avec succès. "
                f"Prix total: {location.montant_total_facture:.2f} DA",
            )
            return redirect("medical:location_bloc_detail", location_id=location.id)

        except Exception as e:
            logger.exception("Erreur lors de la modification de la location")
            errors.append(f"Erreur lors de la modification : {str(e)}")
            return self._render_with_errors(request, location_id, errors)

    def _render_with_errors(self, request, location_id, errors):
        location = get_object_or_404(LocationBloc, id=location_id)
        context = {
            "location": location,
            "patients": Patient.objects.all(),
            "medecins": Medecin.objects.all(),
            "blocs": Bloc.objects.filter(est_actif=True).order_by("nom_bloc"),
            "forfaits": Forfait.objects.filter(est_actif=True)
            .prefetch_related("produits__produit")
            .order_by("nom"),
            "produits": Produit.objects.filter(est_actif=True).order_by("nom"),
            "actes_location": ActeLocation.objects.filter(est_actif=True)
            .prefetch_related("produits_inclus__produit")
            .order_by("nom"),
            "now": timezone.localdate(),
            "errors": errors,
            "form_data": request.POST,
            "actes_selected": location.actes_location.all(),
            "produits_selected": location.consommations_produits.filter(
                est_inclus=False
            ),
        }
        return render(request, "locations/location_edit.html", context)


class LocationBlocDeleteView(View):
    """Vue pour supprimer une location de bloc"""

    def post(self, request, location_id):
        location = get_object_or_404(LocationBloc, id=location_id)

        # Suppression
        nom_acte = location.nom_acte
        date_operation = location.date_operation
        location.delete()

        messages.success(
            request,
            f"Location de bloc '{nom_acte}' du {date_operation.strftime('%d/%m/%Y')} supprimée avec succès.",
        )
        return redirect("medical:location_bloc_list")


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
                "actes": [
                    {
                        "id": fa.acte.id,
                        "nom": fa.acte.nom,
                        "quantite_incluse": fa.quantite,
                        "prix_unitaire_inclus": float(fa.prix_unitaire_inclus),
                        "prix_standard": float(fa.acte.prix),
                        "produits": [
                            {
                                "id": ap.produit.id,
                                "nom": ap.produit.nom,
                                "quantite_standard": ap.quantite_standard,
                                "prix_unitaire": float(ap.produit.prix_vente),
                            }
                            for ap in fa.acte.produits_inclus.all()
                        ],
                    }
                    for fa in forfait.actes_inclus.all()
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


def generate_location_pdf_bytes(location):
    """Génère le PDF en mémoire et retourne les bytes"""
    cache_key = f"pdf_location_{location.id}"
    pdf = cache.get(cache_key)
    if pdf:
        return pdf

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Spacer(1, 12))

    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=30,
        alignment=1,
    )
    story.append(Paragraph(f"DOSSIER #D-{location.id:05d}", title_style))
    story.append(Spacer(1, 12))

    # General Information
    info_data = [
        ["Patient:", getattr(location.patient, "nom_complet", "N/A")],
        [
            "Médecin:",
            f"Dr. {getattr(location.medecin, 'nom_complet', 'N/A')} ({getattr(location.medecin, 'telephone', 'N/A')})",
        ],
        [
            "Date d'intervention:",
            (
                location.date_operation.strftime("%d/%m/%Y")
                if location.date_operation
                else "N/A"
            ),
        ],
        ["Bloc:", getattr(location.bloc, "nom_bloc", "N/A")],
        [
            "Durée:",
            (
                f"{location.duree_reelle} minutes"
                if location.duree_reelle
                else "Non définie"
            ),
        ],
    ]

    info_table = Table(info_data, colWidths=[0.3 * doc.width, 0.7 * doc.width])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 20))

    # Prestations Table
    prestations_data = [["Description", "Quantité", "Prix unitaire", "Montant"]]

    if location.type_tarification == "FORFAIT":
        desc = (
            f"Forfait {getattr(location.forfait, 'nom', 'Forfait')}"
            if location.forfait
            else "Forfait"
        )
    else:
        desc = f"Location bloc {getattr(location.bloc, 'nom_bloc', 'N/A')}"

    prestations_data.append(
        [
            desc,
            "1",
            (
                f"{location.prix_final:.2f} DA"
                if location.prix_final is not None
                else "0.00 DA"
            ),
            (
                f"{location.prix_final:.2f} DA"
                if location.prix_final is not None
                else "0.00 DA"
            ),
        ]
    )

    # Actes supplémentaires
    for acte_location in location.actes_location.all():
        prestations_data.append(
            [
                getattr(acte_location.acte, "nom", "N/A"),
                str(acte_location.quantite or 1),
                (
                    f"{acte_location.prix_unitaire:.2f} DA"
                    if acte_location.prix_unitaire is not None
                    else "0.00 DA"
                ),
                (
                    f"{acte_location.prix_total:.2f} DA"
                    if acte_location.prix_total is not None
                    else "0.00 DA"
                ),
            ]
        )

    # Produits supplémentaires
    consommations = getattr(
        location, "prefetched_consommations", location.consommations.all()
    )
    for consommation in consommations:
        if consommation.source_inclusion == "SUPPLEMENTAIRE" or (
            hasattr(consommation, "ecart_quantite") and consommation.ecart_quantite > 0
        ):
            if consommation.source_inclusion == "SUPPLEMENTAIRE":
                prestations_data.append(
                    [
                        f"{getattr(consommation.produit, 'nom', 'N/A')} (Supplémentaire)",
                        (
                            f"{consommation.quantite:.1f}"
                            if consommation.quantite is not None
                            else "0.0"
                        ),
                        (
                            f"{consommation.prix_unitaire:.2f} DA"
                            if consommation.prix_unitaire is not None
                            else "0.00 DA"
                        ),
                        (
                            f"{consommation.prix_total:.2f} DA"
                            if consommation.prix_total is not None
                            else "0.00 DA"
                        ),
                    ]
                )
            else:
                prestations_data.append(
                    [
                        f"{getattr(consommation.produit, 'nom', 'N/A')} (Écart)",
                        (
                            f"{consommation.ecart_quantite:.1f}"
                            if consommation.ecart_quantite is not None
                            else "0.0"
                        ),
                        (
                            f"{consommation.prix_unitaire:.2f} DA"
                            if consommation.prix_unitaire is not None
                            else "0.00 DA"
                        ),
                        (
                            f"{consommation.prix_facturable:.2f} DA"
                            if consommation.prix_facturable is not None
                            else "0.00 DA"
                        ),
                    ]
                )

    # Ligne total
    prestations_data.append(
        [
            "TOTAL À PAYER (TTC)",
            "",
            "",
            (
                f"{location.montant_total_facture:.2f} DA"
                if location.montant_total_facture is not None
                else "0.00 DA"
            ),
        ]
    )

    prestations_table = Table(
        prestations_data,
        colWidths=[
            0.4 * doc.width,
            0.15 * doc.width,
            0.225 * doc.width,
            0.225 * doc.width,
        ],
    )
    prestations_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, -2), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 12),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    story.append(prestations_table)
    story.append(Spacer(1, 20))

    # Footer
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=8, alignment=1
    )

    story.append(Paragraph("Nous vous remercions pour votre confiance", footer_style))
    story.append(Paragraph("Clinique INAYA", footer_style))
    story.append(Paragraph("Service Comptabilité", footer_style))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    # Cache the PDF for 1 hour
    cache.set(cache_key, pdf, timeout=3600)
    return pdf


class LocationBlocExportPDFView(PermissionRequiredMixin, View):
    """Export PDF de la facture de location de bloc"""

    permission_required = "medical.view_locationbloc"

    def get(self, request, location_id):
        try:
            qs = LocationBloc.objects.select_related(
                "bloc", "patient", "medecin", "forfait"
            )
            consommations_prefetch = Prefetch(
                "consommations",
                queryset=ConsommationProduitBloc.objects.select_related(
                    "produit", "acte_associe"
                ),
                to_attr="prefetched_consommations",
            )
            qs = qs.prefetch_related(consommations_prefetch)
            location = get_object_or_404(qs, id=location_id)

            pdf = generate_location_pdf_bytes(location)
            logger.info(f"PDF generated successfully for LocationBloc {location_id}")

            response = HttpResponse(content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="Facture_BL-{location.id:05d}.pdf"'
            )
            response.write(pdf)
            return response
        except Exception as e:
            logger.error(
                f"Error generating PDF for LocationBloc {location_id}: {str(e)}",
                exc_info=True,
            )
            return HttpResponse(status=500)


@login_required
def send_location_invoice_whatsapp(request, location_id):
    try:
        logger.info(f"Processing WhatsApp send for LocationBloc {location_id}")
        location = get_object_or_404(LocationBloc, id=location_id)
        phone = getattr(location.medecin, "telephone", "")

        # Normalize phone number: add +213 if no country code
        if phone and not phone.startswith("+"):
            phone = f"+213{phone}"
            logger.info(
                f"Normalized phone number for LocationBloc {location_id}: {phone}"
            )

        # Validate phone number
        if not phone or not re.match(r"^\+\d{9,15}$", phone):
            logger.error(
                f"Invalid phone number for LocationBloc {location_id}: {phone}"
            )
            return JsonResponse(
                {"ok": False, "error": "Numéro de téléphone du médecin invalide"},
                status=400,
            )

        # Construct invoice details message
        message = (
            f"Bonjour Dr. {getattr(location.medecin, 'nom_complet', 'N/A')},\n\n"
            f"Voici les détails de dossier-{location.id:05d}* :\n\n"
            f"**Patient** : {getattr(location.patient, 'nom_complet', 'N/A')}\n"
            f"**Date** : {location.date_operation.strftime('%d/%m/%Y') if location.date_operation else 'N/A'}\n"
            f"**Bloc** : {getattr(location.bloc, 'nom_bloc', 'N/A')}\n"
            f"**Durée** : {location.duree_reelle} min{' (*' + location.forfait.nom + '*)' if location.type_tarification == 'FORFAIT' and location.forfait else ' (*' + location.nom_acte + '*)'}\n\n"
            f"**Détails des prestations** :\n"
        )

        # Base pricing (Forfait or Bloc)
        if location.type_tarification == "FORFAIT":
            desc = (
                f"Forfait {getattr(location.forfait, 'nom', 'Forfait')}"
                if location.forfait
                else "Forfait"
            )
        else:
            desc = f"Location bloc {getattr(location.bloc, 'nom_bloc', 'N/A')}"
        message += f"- {desc} : 1 x {location.prix_final:,.2f} DA = {location.prix_final:,.2f} DA\n"

        # Actes supplémentaires
        for acte_location in location.actes_location.all():
            message += (
                f"- {getattr(acte_location.acte, 'nom', 'N/A')} (Acte) : "
                f"{acte_location.quantite or 1} x {acte_location.prix_unitaire:,.2f} DA = "
                f"{acte_location.prix_total:,.2f} DA\n"
            )

        # Produits supplémentaires
        consommations = getattr(
            location, "prefetched_consommations", location.consommations.all()
        )
        for consommation in consommations:
            if consommation.source_inclusion == "SUPPLEMENTAIRE" or (
                hasattr(consommation, "ecart_quantite")
                and consommation.ecart_quantite > 0
            ):
                if consommation.source_inclusion == "SUPPLEMENTAIRE":
                    message += (
                        f"- {getattr(consommation.produit, 'nom', 'N/A')} (Supplémentaire) : "
                        f"{consommation.quantite:.1f} x {consommation.prix_unitaire:,.2f} DA = "
                        f"{consommation.prix_total:,.2f} DA\n"
                    )
                else:
                    message += (
                        f"- {getattr(consommation.produit, 'nom', 'N/A')} (Écart) : "
                        f"{consommation.ecart_quantite:.1f} x {consommation.prix_unitaire:,.2f} DA = "
                        f"{consommation.prix_facturable:,.2f} DA\n"
                    )

        # Total and closing
        message += (
            f"\n**Total à payer (TTC)** : {location.montant_total_facture:,.2f} DA\n\n"
            f"Nous vous remercions pour votre confiance.\n"
            f"Clinique INAYA - Service Comptabilité"
        )

        # Log message length for debugging
        logger.info(f"WhatsApp message length: {len(message)} characters")

        whatsapp_url = f"https://wa.me/{phone}?text={quote(message)}"
        logger.info(f"Redirecting to WhatsApp URL: {whatsapp_url}")
        return redirect(whatsapp_url)
    except Exception as e:
        logger.error(
            f"Error sending WhatsApp for LocationBloc {location_id}: {str(e)}",
            exc_info=True,
        )
        return JsonResponse(
            {"ok": False, "error": "Erreur lors de l'envoi via WhatsApp"}, status=500
        )


@staff_member_required
@csrf_protect
def marquer_reglement_surplus(request, location_id):
    """Marquer qu'un surplus a été versé au médecin"""
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"}, status=405
        )

    try:
        location = get_object_or_404(LocationBloc, id=location_id)

        # Vérifier que la location a effectivement un surplus à verser
        if location.statut_paiement != "SURPLUS_CLINIQUE":
            return JsonResponse(
                {
                    "success": False,
                    "error": "Cette location n'a pas de surplus à verser",
                },
                status=400,
            )

        if location.date_reglement_surplus:
            return JsonResponse(
                {"success": False, "error": "Le surplus a déjà été marqué comme versé"},
                status=400,
            )

        # Récupérer la date de règlement (ou utiliser aujourd'hui)
        data = json.loads(request.body) if request.body else {}
        date_reglement_str = data.get(
            "date_reglement", timezone.localdate().isoformat()
        )
        date_reglement = parse_date(date_reglement_str)

        if not date_reglement:
            return JsonResponse(
                {"success": False, "error": "Date invalide"}, status=400
            )

        # Marquer le règlement
        location.date_reglement_surplus = date_reglement
        location.save()

        # Log de l'action
        logger.info(
            f"Surplus de {location.surplus_a_verser} DA marqué comme versé pour "
            f"la location {location.id} par {request.user.username}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Surplus de {location.surplus_a_verser} DA marqué comme versé",
                "date_reglement": date_reglement.strftime("%d/%m/%Y"),
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors du marquage du règlement surplus pour location {location_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@staff_member_required
@csrf_protect
def marquer_reglement_complement(request, location_id):
    """Marquer qu'un complément a été payé par le médecin"""
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"}, status=405
        )

    try:
        location = get_object_or_404(LocationBloc, id=location_id)

        # Vérifier que la location a effectivement un complément à recevoir
        if location.statut_paiement != "COMPLEMENT_MEDECIN":
            return JsonResponse(
                {
                    "success": False,
                    "error": "Cette location n'a pas de complément à recevoir",
                },
                status=400,
            )

        if location.date_reglement_complement:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Le complément a déjà été marqué comme payé",
                },
                status=400,
            )

        # Récupérer la date de règlement (ou utiliser aujourd'hui)
        data = json.loads(request.body) if request.body else {}
        date_reglement_str = data.get(
            "date_reglement", timezone.localdate().isoformat()
        )
        date_reglement = parse_date(date_reglement_str)

        if not date_reglement:
            return JsonResponse(
                {"success": False, "error": "Date invalide"}, status=400
            )

        # Marquer le règlement
        location.date_reglement_complement = date_reglement
        location.save()

        # Log de l'action
        logger.info(
            f"Complément de {location.complement_du_medecin} DA marqué comme payé pour "
            f"la location {location.id} par {request.user.username}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Complément de {location.complement_du_medecin} DA marqué comme payé",
                "date_reglement": date_reglement.strftime("%d/%m/%Y"),
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors du marquage du règlement complément pour location {location_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@staff_member_required
def modifier_paiement_location(request, location_id):
    """Vue pour modifier les informations de paiement d'une location existante"""
    location = get_object_or_404(LocationBloc, id=location_id)

    if request.method == "POST":
        try:
            nouveau_montant_str = request.POST.get("nouveau_montant_paye")
            nouvelles_notes = request.POST.get("nouvelles_notes_paiement", "").strip()

            if nouveau_montant_str:
                nouveau_montant = Decimal(nouveau_montant_str)
                if nouveau_montant < 0:
                    messages.error(request, "Le montant payé ne peut pas être négatif.")
                    return redirect(
                        "medical:location_bloc_detail", location_id=location.id
                    )

                # Sauvegarder l'ancien montant pour le log
                ancien_montant = location.montant_paye_caisse

                # Mettre à jour les informations
                location.montant_paye_caisse = nouveau_montant
                location.notes_paiement = nouvelles_notes

                # Réinitialiser les dates de règlement si le statut change
                ancien_statut = location.statut_paiement
                location.calculer_paiements(nouveau_montant)

                if ancien_statut != location.statut_paiement:
                    location.date_reglement_surplus = None
                    location.date_reglement_complement = None

                location.save()

                # Log de la modification
                logger.info(
                    f"Paiement modifié pour la location {location.id} par {request.user.username}: "
                    f"{ancien_montant} DA → {nouveau_montant} DA"
                )

                messages.success(
                    request,
                    f"Informations de paiement mises à jour. "
                    f"Nouveau statut: {location.get_statut_paiement_display()}",
                )
            else:
                messages.error(request, "Montant invalide")

        except (ValueError, InvalidOperation):
            messages.error(request, "Format de montant invalide")
        except Exception as e:
            logger.exception(
                f"Erreur lors de la modification du paiement pour location {location_id}"
            )
            messages.error(request, f"Erreur lors de la mise à jour: {str(e)}")

    return redirect("medical:location_bloc_detail", location_id=location.id)


@login_required
def locations_en_attente_reglement(request):
    """Vue pour lister les locations avec des règlements en attente"""

    # Locations avec surplus à verser
    surplus_en_attente = (
        LocationBloc.objects.filter(
            statut_paiement="SURPLUS_CLINIQUE", date_reglement_surplus__isnull=True
        )
        .select_related("patient", "medecin", "bloc")
        .order_by("-date_operation")
    )

    # Locations avec complément à recevoir
    complement_en_attente = (
        LocationBloc.objects.filter(
            statut_paiement="COMPLEMENT_MEDECIN", date_reglement_complement__isnull=True
        )
        .select_related("patient", "medecin", "bloc")
        .order_by("-date_operation")
    )

    # Calculs des totaux
    total_surplus_a_verser = sum(loc.surplus_a_verser for loc in surplus_en_attente)
    total_complement_a_recevoir = sum(
        loc.complement_du_medecin for loc in complement_en_attente
    )

    context = {
        "surplus_en_attente": surplus_en_attente,
        "complement_en_attente": complement_en_attente,
        "total_surplus_a_verser": total_surplus_a_verser,
        "total_complement_a_recevoir": total_complement_a_recevoir,
        "solde_net": total_complement_a_recevoir - total_surplus_a_verser,
    }

    return render(request, "locations/reglements_en_attente.html", context)
