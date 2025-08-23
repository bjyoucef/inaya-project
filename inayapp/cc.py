# medical/views/bloc_location.py

import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from medecin.models import Medecin
from medical.models import PrestationKt
from medical.models.bloc_location import (ActeLocation, ActeProduitInclus,
                                          Bloc, BlocProduitInclus,
                                          ConsommationProduitBloc, Forfait,
                                          ForfaitProduitInclus, LocationBloc,
                                          LocationBlocActe)
from patients.models import Patient
from pharmacies.models import Produit

logger = logging.getLogger(__name__)


class LocationBlocCreateView(View):
    """Création d'une location de bloc avec gestion automatique des produits inclus"""

    def get(self, request):
        # Préparer les données pour le frontend JavaScript
        blocs_data = {}
        for bloc in Bloc.objects.filter(est_actif=True).prefetch_related('produits_inclus__produit'):
            blocs_data[str(bloc.id)] = {
                'prix_base': float(bloc.prix_base),
                'prix_supplement_30min': float(bloc.prix_supplement_30min),
                'produits_inclus': [
                    {
                        'id': bp.produit.id,
                        'nom': bp.produit.nom,
                        'quantite_defaut': bp.quantite,
                        'prix_unitaire': float(bp.produit.prix_vente)
                    }
                    for bp in bloc.produits_inclus.all()
                ]
            }

        # Données des actes avec leurs produits inclus
        actes_data = []
        for acte in ActeLocation.objects.filter(est_actif=True).prefetch_related('produits_inclus__produit'):
            actes_data.append({
                'id': acte.id,
                'nom': acte.nom,
                'prix': float(acte.prix),
                'produits_inclus': [
                    {
                        'id': ap.produit.id,
                        'nom': ap.produit.nom,
                        'quantite_defaut': ap.quantite_standard,
                        'prix_unitaire': float(ap.produit.prix_vente)
                    }
                    for ap in acte.produits_inclus.all()
                ]
            })

        # Données des forfaits avec leurs produits inclus
        forfaits_data = {}
        for forfait in Forfait.objects.filter(est_actif=True).prefetch_related('produits__produit'):
            forfaits_data[str(forfait.id)] = {
                'prix': float(forfait.prix),
                'duree': forfait.duree,
                'produits_inclus': [
                    {
                        'id': fp.produit.id,
                        'nom': fp.produit.nom,
                        'quantite_defaut': fp.quantite,
                        'prix_unitaire': float(fp.produit.prix_vente)
                    }
                    for fp in forfait.produits.all()
                ]
            }

        context = {
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
            # Données JSON pour JavaScript
            "blocs_data_json": json.dumps(blocs_data),
            "actes_data_json": json.dumps(actes_data),
            "forfaits_data_json": json.dumps(forfaits_data),
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
                if quantite_reelle >= 0:  # Permettre 0 pour marquer comme non consommé
                    produits_inclus_data.append({
                        "produit_id": produit_id,
                        "quantite_reelle": quantite_reelle
                    })
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
                    produit_acte_ids = request.POST.getlist(f"actes[{i}][produits][]") or []
                    quantites_acte_produits = request.POST.getlist(f"actes[{i}][quantites_reelles][]") or []
                    prix_acte_produits = request.POST.getlist(f"actes[{i}][prix_unitaire][]") or []

                    for j, prod_id in enumerate(produit_acte_ids):
                        if prod_id:
                            try:
                                qte_reelle = float(quantites_acte_produits[j]) if j < len(quantites_acte_produits) else 0
                                prix_unit = float(prix_acte_produits[j]) if j < len(prix_acte_produits) else 0
                                acte_produits.append({
                                    "produit_id": prod_id,
                                    "quantite_reelle": qte_reelle,
                                    "prix_unitaire": prix_unit
                                })
                            except (ValueError, IndexError):
                                continue

                    actes_data.append({
                        "acte_id": acte_id,
                        "quantite": quantite,
                        "prix": prix,
                        "produits": acte_produits
                    })
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

        # ACTION = CALCULATE : calculer le prix sans sauvegarder
        if action == "calculate":
            try:
                # Logique de calcul similaire à la version précédente
                # mais en tenant compte des quantités réelles ajustées
                bloc = get_object_or_404(Bloc, id=bloc_id)
                forfait = (
                    get_object_or_404(Forfait, id=forfait_id) if forfait_id else None
                )

                # Déterminer la durée à utiliser pour le calcul
                duree_calcul = duree_reelle or 90

                # Calcul du prix de base selon le type de tarification
                prix_bloc = Decimal(0)

                if type_tarification == "FORFAIT" and forfait:
                    prix_bloc = Decimal(forfait.prix)
                    # Ajouter le supplément si dépassement
                    if duree_calcul > forfait.duree:
                        minutes_supp = duree_calcul - forfait.duree
                        tranches = (minutes_supp + 29) // 30
                        prix_bloc += Decimal(tranches) * Decimal(
                            bloc.prix_supplement_30min
                        )
                else:  # DUREE
                    prix_bloc = Decimal(bloc.prix_base)
                    if duree_calcul > 90:
                        minutes_supp = duree_calcul - 90
                        tranches = (minutes_supp + 29) // 30
                        prix_bloc += Decimal(tranches) * Decimal(
                            bloc.prix_supplement_30min
                        )

                # Calcul de l'impact des écarts sur les produits inclus
                impact_produits_inclus = Decimal(0)
                for prod_data in produits_inclus_data:
                    try:
                        produit = Produit.objects.get(id=prod_data["produit_id"])
                        # Trouver la quantité incluse dans le bloc/forfait
                        quantite_incluse = 0
                        if type_tarification == "DUREE":
                            try:
                                bp = BlocProduitInclus.objects.get(bloc=bloc, produit=produit)
                                quantite_incluse = bp.quantite
                            except BlocProduitInclus.DoesNotExist:
                                pass
                        elif forfait:
                            try:
                                fp = ForfaitProduitInclus.objects.get(forfait=forfait, produit=produit)
                                quantite_incluse = fp.quantite
                            except ForfaitProduitInclus.DoesNotExist:
                                pass
                        
                        ecart = prod_data["quantite_reelle"] - quantite_incluse
                        impact_produits_inclus += Decimal(ecart) * Decimal(produit.prix_vente)
                    except Produit.DoesNotExist:
                        continue

                # Calcul du montant des actes et impact de leurs produits
                montant_actes = Decimal(0)
                impact_produits_actes = Decimal(0)
                for acte_data in actes_data:
                    try:
                        acte = ActeLocation.objects.get(id=acte_data["acte_id"])
                        prix_unitaire = (
                            acte_data["prix"] if acte_data["prix"] else acte.prix
                        )
                        montant_actes += Decimal(acte_data["quantite"]) * prix_unitaire

                        # Calculer l'impact des produits de l'acte
                        for prod_acte in acte_data["produits"]:
                            try:
                                produit = Produit.objects.get(id=prod_acte["produit_id"])
                                # Quantité incluse = quantité standard * quantité d'actes
                                try:
                                    ap = ActeProduitInclus.objects.get(acte=acte, produit=produit)
                                    quantite_incluse = ap.quantite_standard * acte_data["quantite"]
                                    ecart = prod_acte["quantite_reelle"] - quantite_incluse
                                    impact_produits_actes += Decimal(ecart) * Decimal(produit.prix_vente)
                                except ActeProduitInclus.DoesNotExist:
                                    # Produit ajouté manuellement, facturer entièrement
                                    impact_produits_actes += Decimal(prod_acte["quantite_reelle"]) * Decimal(prod_acte["prix_unitaire"])
                            except Produit.DoesNotExist:
                                continue
                    except ActeLocation.DoesNotExist:
                        continue

                # Calcul du montant des produits supplémentaires
                montant_produits_supp = Decimal(0)
                for ps in produits_supp:
                    montant_produits_supp += Decimal(ps["quantite"]) * Decimal(ps["prix_unitaire"])

                # Total estimé
                total_estime = prix_bloc + montant_actes + impact_produits_inclus + impact_produits_actes + montant_produits_supp

                # Préparer le détail pour l'affichage
                detail = {
                    "prix_bloc": float(prix_bloc),
                    "montant_actes": float(montant_actes),
                    "impact_produits_inclus": float(impact_produits_inclus),
                    "impact_produits_actes": float(impact_produits_actes),
                    "montant_produits_supp": float(montant_produits_supp),
                    "total_estime": float(total_estime),
                    "type": type_tarification,
                }

                context = self.get(request).context_data
                context.update(
                    {
                        "form_data": request.POST,
                        "prix_calcule": detail,
                        "show_price": True,
                    }
                )

                return render(request, "locations/location_create.html", context)

            except Exception as e:
                logger.exception("Erreur lors du calcul")
                errors.append(f"Erreur lors du calcul : {str(e)}")
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
            )

            # Le prix sera calculé automatiquement dans le save() du modèle
            location.save()

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
                        bloc_produit.quantite  # valeur par défaut si pas spécifiée
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
                            ecart_quantite=ecart
                        )

            # 2. Produits inclus dans le forfait (avec quantités ajustées)
            if type_tarification == "FORFAIT" and forfait:
                quantites_reelles_dict = {
                    int(p["produit_id"]): p["quantite_reelle"] 
                    for p in produits_inclus_data
                }
                
                for forfait_produit in forfait.produits.all():
                    quantite_reelle = quantites_reelles_dict.get(
                        forfait_produit.produit.id,
                        forfait_produit.quantite  # valeur par défaut
                    )
                    
                    ecart = quantite_reelle - forfait_produit.quantite
                    
                    if quantite_reelle > 0:
                        ConsommationProduitBloc.objects.create(
                            location=location,
                            produit=forfait_produit.produit,
                            quantite=quantite_reelle,
                            prix_unitaire=Decimal(forfait_produit.produit.prix_vente),
                            est_inclus=(ecart <= 0),
                            source_inclusion="FORFAIT",
                            quantite_incluse=forfait_produit.quantite,
                            ecart_quantite=ecart
                        )

            # 3. Créer les associations avec les actes supplémentaires
            montant_total_actes = Decimal(0)
            for acte_data in actes_data:
                try:
                    acte = ActeLocation.objects.get(id=acte_data["acte_id"])
                    prix_unitaire = (
                        acte_data["prix"] if acte_data["prix"] else acte.prix
                    )

                    # Créer l'association acte-location
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
                            produit = Produit.objects.get(id=prod_acte_data["produit_id"])
                            quantite_reelle = prod_acte_data["quantite_reelle"]
                            
                            # Vérifier si c'est un produit inclus dans l'acte
                            try:
                                acte_produit_inclus = ActeProduitInclus.objects.get(
                                    acte=acte, 
                                    produit=produit
                                )
                                # Quantité incluse = quantité standard * nombre d'actes
                                quantite_incluse = acte_produit_inclus.quantite_standard * acte_data["quantite"]
                                ecart = quantite_reelle - quantite_incluse
                                est_inclus = (ecart <= 0)
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
                                    prix_unitaire=Decimal(prod_acte_data["prix_unitaire"]),
                                    est_inclus=est_inclus,
                                    source_inclusion=source,
                                    quantite_incluse=quantite_incluse,
                                    ecart_quantite=ecart,
                                    acte_associe=location_acte  # Lien vers l'acte
                                )

                        except Produit.DoesNotExist:
                            logger.error(f"Produit d'acte introuvable: {prod_acte_data['produit_id']}")
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
                        ecart_quantite=ps["quantite"]  # Tout est en écart
                    )
                    logger.info(
                        f"Ajout produit supplémentaire: {prod.nom} x{ps['quantite']}"
                    )
                except Produit.DoesNotExist:
                    logger.error(f"Produit supplémentaire introuvable: {ps['produit_id']}")
                    continue

            # Calculer le prix total final
            prix_total = location.montant_total_facture

            # Message de succès avec détail
            impact_ecarts = sum(
                c.prix_total for c in location.consommations.filter(ecart_quantite__gt=0)
            ) - sum(
                abs(c.prix_total) for c in location.consommations.filter(ecart_quantite__lt=0)
            )

            messages.success(
                request,
                f"Location de bloc créée avec succès pour le {date_operation.strftime('%d/%m/%Y')}. "
                f"Prix total: {prix_total:.2f} DA "
                f"(Bloc: {location.prix_final:.2f} DA, "
                f"Actes: {location.montant_total_actes:.2f} DA, "
                f"Impact écarts produits: {impact_ecarts:.2f} DA, "
                f"Produits supp.: {location.montant_total_produits_supplementaires:.2f} DA)",
            )

            return redirect("medical:location_bloc_detail", location_id=location.id)

        except Exception as e:
            logger.exception("Erreur lors de la création de la location")
            errors.append(f"Erreur lors de la création : {str(e)}")
            return self._render_with_errors(request, errors)


# Vue AJAX pour récupérer les produits d'un acte avec leurs quantités par défaut
@login_required
def get_acte_produits(request, acte_id):
    """Retourne les produits inclus dans un acte avec leurs quantités par défaut"""
    try:
        acte = get_object_or_404(ActeLocation, id=acte_id)
        produits = []
        
        for acte_produit in acte.produits_inclus.all():
            produits.append({
                'id': acte_produit.produit.id,
                'nom': acte_produit.produit.nom,
                'code_produit': acte_produit.produit.code_produit or '',
                'quantite_defaut': acte_produit.quantite_standard,
                'prix_vente': float(acte_produit.produit.prix_vente),
                'est_obligatoire': acte_produit.est_obligatoire
            })
        
        return JsonResponse({
            'success': True,
            'acte': {
                'id': acte.id,
                'nom': acte.nom,
                'prix': float(acte.prix)
            },
            'produits': produits
        })
        
    except Exception as e:
        logger.exception(f"Erreur lors de la récupération des produits de l'acte {acte_id}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Vue pour récupérer les produits d'un bloc avec leurs quantités par défaut
@login_required
def get_bloc_produits(request, bloc_id):
    """Retourne les produits inclus dans un bloc avec leurs quantités par défaut"""
    try:
        bloc = get_object_or_404(Bloc, id=bloc_id)
        produits = []

        for bloc_produit in bloc.produits_inclus.all():
            produits.append({
                'id': bloc_produit.produit.id,
                'nom': bloc_produit.produit.nom,
                'code_produit': bloc_produit.produit.code_produit or '',
                'quantite_defaut': bloc_produit.quantite,
                'prix_vente': float(bloc_produit.produit.prix_vente)
            })

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


# Vue pour récupérer les produits d'un forfait
@login_required
def get_forfait_produits(request, forfait_id):
    """Retourne les produits inclus dans un forfait avec leurs quantités par défaut"""
    try:
        forfait = get_object_or_404(Forfait, id=forfait_id)
        produits = []

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
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des produits du forfait {forfait_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)
