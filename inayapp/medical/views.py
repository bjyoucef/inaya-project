import copy
import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from accueil.models import ConfigDate
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import ExpressionWrapper, F, Prefetch, Q, Sum, Value
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views import View
from finance.models import Convention, TarifActe, TarifActeConvention
from medecin.models import Medecin
from medical.models import (Acte, ActeProduit, ConsommationProduit, Prestation,
                            PrestationActe, PrestationAudit)
from medical.models.actes import ActeProduit
from patients.models import Patient
from pharmacies.models import ConsommationProduit, Produit
from utils.utils import services_autorises


class GetTarifView(View):
    def get(self, request):
        acte_id = request.GET.get("acte_id")
        convention_id = request.GET.get("convention_id")
        tarif = Decimal("0.00")

        try:
            acte = Acte.objects.get(pk=acte_id)

            if convention_id:
                convention = Convention.objects.get(pk=convention_id)
                tac = (
                    TarifActeConvention.objects.filter(acte=acte, convention=convention)
                    .order_by("-date_effective")
                    .first()
                )
                if tac:
                    tarif = tac.tarif_acte.montant

            else:
                # d'abord le tarif explicite par défaut
                ta = TarifActe.objects.filter(acte=acte, is_default=True).first()
                if not ta:
                    # sinon le plus récent
                    ta = (
                        TarifActe.objects.filter(acte=acte)
                        .order_by("-date_effective")
                        .first()
                    )
                if ta:
                    tarif = ta.montant

            return JsonResponse({"tarif": float(tarif)})

        except Acte.DoesNotExist:
            return JsonResponse({"error": "Acte introuvable"}, status=404)
        except Convention.DoesNotExist:
            return JsonResponse({"error": "Convention introuvable"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


class GetActeProduitsView(View):
    def get(self, request, acte_id):
        acte = get_object_or_404(Acte, id=acte_id)
        produits = acte.produits_defaut.select_related("produit").all()
        data = [
            {
                "id": ap.produit.id,
                "nom": ap.produit.nom,
                "code": ap.produit.code_produit,
                "quantite_defaut": ap.quantite_defaut,
                "prix_vente": float(ap.produit.prix_vente),
            }
            for ap in produits
        ]
        return JsonResponse({"produits": data})


class PrestationCreateView(View):
    def get(self, request):
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()

        # Récupère tous les produits actifs pour initialiser le JS
        all_prods = Produit.objects.filter(est_actif=True)

        # Services autorisés par l'utilisateur
        services = services_autorises(request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = Acte.objects.prefetch_related("conventions").filter(
            service__id__in=service_ids
        )
        actes_data = [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(acte.conventions.all().values("id", "nom")),
            }
            for acte in actes
        ]

        # Prépare le contexte
        context = {
            "patients": patients,
            "medecins": medecins,
            "statut_choices": Prestation.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "now": timezone.localdate(),
            # Pour la gestion dynamique des produits
            "all_produits": all_prods,
            "all_produits_json": json.dumps([
                { **prod, "prix_vente": float(prod["prix_vente"]) }
                for prod in all_prods.values("id", "code_produit", "nom", "prix_vente")
            ]),
        }

        return render(request, "prestations/create.html", context)

    @transaction.atomic
    def post(self, request):
        errors = []
        # Champs obligatoires
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        date_str = request.POST.get("date_prestation")
        statut = request.POST.get("statut")
        observations = request.POST.get("observations", "").strip()

        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        conv_ok_vals = request.POST.getlist("convention_accordee[]")
        total_consommations = Decimal("0.00")

        if not (patient_id and medecin_id and date_str and statut):
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Conversion de la date
        try:
            date_prest = timezone.datetime.strptime(date_str, "%Y-%m-%d")
            # Make it timezone-aware
            if timezone.is_naive(date_prest):
                date_prest = timezone.make_aware(date_prest)
        except (ValueError, TypeError):
            errors.append("Format de date invalide.")

        prestation_data = []
        conso_data = []
        total = Decimal("0.00")

        # Validation des actes
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = Acte.objects.get(pk=acte_pk)
                conv = None
                conv_ok = False
                if convention_ids and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    conv_ok = conv_ok_vals[idx] == "oui"

                tarif = Decimal(tarifs[idx] or "0")
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                    }
                )

                # Récupération des consommations par acte
                prod_field = f"actes[{idx}][produits][]"
                qty_field = f"actes[{idx}][quantites_reelles][]"
                for pid, qty in zip(
                    request.POST.getlist(prod_field), request.POST.getlist(qty_field)
                ):
                    conso_data.append(
                        {
                            "idx": idx,
                            "produit_id": pid,
                            "quantite_reelle": qty,
                        }
                    )

            except Acte.DoesNotExist:
                errors.append(f"Acte invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            return render(
                request,
                "prestations/create.html",
                {
                    "errors": errors,
                    "patients": Patient.objects.all(),
                    "medecins": Medecin.objects.all(),
                    "statut_choices": Prestation.STATUT_CHOICES,
                    "actes_json": json.dumps(prestation_data),
                    "now": timezone.localdate(),
                },
            )

        # Création de la prestation
        prestation = Prestation.objects.create(
            patient_id=patient_id,
            medecin_id=medecin_id,
            date_prestation=date_prest,
            statut=statut,
            observations=observations,
            prix_total=total,
            prix_supplementaire=Decimal(request.POST.get("prix_supplementaire", "0")),
        )

        # Création des PrestationActe et consommations
        for idx, d in enumerate(prestation_data):
            pa = PrestationActe.objects.create(
                prestation=prestation,
                acte=d["acte"],
                convention=d["convention"],
                convention_accordee=d["convention_accordee"],
                tarif_conventionne=d["tarif"],
                
            )
            for c in [c for c in conso_data if c["idx"] == idx]:
                if not c["produit_id"] or int(c["quantite_reelle"]) <= 0:
                    continue
                prod = get_object_or_404(Produit, id=c["produit_id"])
                quantite_reelle = int(c["quantite_reelle"])
                montant_conso = quantite_reelle * prod.prix_vente
                total_consommations += montant_conso  # Ajouter ce calcul
                try:
                    acte_produit = ActeProduit.objects.get(
                        acte=d["acte"],
                        produit=prod
                    )
                    qte_defaut = acte_produit.quantite_defaut
                except ActeProduit.DoesNotExist:
                    qte_defaut = 0

                ConsommationProduit.objects.create(
                    prestation_acte=pa,
                    produit=prod,
                    quantite_defaut=qte_defaut,
                    quantite_reelle=quantite_reelle,
                    prix_unitaire=prod.prix_vente,

                )

        # Mise à jour du stock
        prestation.update_stock()
        return redirect("medical:prestation_detail", prestation_id=prestation.id)


class PrestationListView(View):
    def get(self, request):
        # --- Récupération / mise à jour de la config date
        config, _ = ConfigDate.objects.get_or_create(
            user=request.user,
            page="prestation",
            defaults={"start_date": date.today(), "end_date": date.today()},
        )
        for param in ("start_date", "end_date"):
            val = request.GET.get(param)
            if val:
                try:
                    setattr(config, param, datetime.strptime(val, "%Y-%m-%d").date())
                except ValueError:
                    pass
        config.save()
        start_date, end_date = (config.start_date, config.end_date)

        # --- Services autorisés
        services = services_autorises(request.user)
        service_ids = services.values_list("id", flat=True)

        # --- Filtrage dynamique
        prestations = (
            Prestation.objects.filter(actes__service__id__in=service_ids)
            .select_related("patient", "medecin")
            .prefetch_related("actes_details__acte")
            .order_by("-date_prestation")
            .distinct()
        )

        # Dictionnaire mapping GET → ORM lookup
        filtres = {
            "status": ("statut", None),
            "medecin": ("medecin_id", int),
            "patient": ("patient_id", int),
            "service": ("actes__service__id", int),
        }

        for param, (field, caster) in filtres.items():
            val = request.GET.get(param)
            if not val:
                continue
            # Pour 'service', on valide en plus l'autorisation
            if param == "service":
                sid = caster(val)
                if sid not in service_ids:
                    prestations = prestations.none()
                    break
                prestations = prestations.filter(**{field: sid})
                continue
            # Typage éventuel
            try:
                val = caster(val) if caster else val
            except (ValueError, TypeError):
                continue
            prestations = prestations.filter(**{field: val})

        # Filtre de date
        if start_date:
            prestations = prestations.filter(date_prestation__gte=start_date)
        if end_date:
            prestations = prestations.filter(date_prestation__lte=end_date)

        # === PAGINATION ===
        # Nombre d'éléments par page (configurable)
        items_per_page = request.GET.get("per_page", 10)
        try:
            items_per_page = int(items_per_page)
            # Limiter entre 10 et 100 pour éviter les abus
            items_per_page = max(10, min(100, items_per_page))
        except (ValueError, TypeError):
            items_per_page = 25

        # Création du paginator
        paginator = Paginator(prestations, items_per_page)

        # Récupération du numéro de page
        page_number = request.GET.get("page", 1)

        try:
            page_obj = paginator.get_page(page_number)
        except PageNotAnInteger:
            # Si page n'est pas un entier, afficher la première page
            page_obj = paginator.get_page(1)
        except EmptyPage:
            # Si page est hors limite, afficher la dernière page
            page_obj = paginator.get_page(paginator.num_pages)

        # Context pour template
        context = {
            "paginator": paginator,
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "items_per_page": items_per_page,
            "total_count": paginator.count,
            
            "medecins": Medecin.objects.filter(prestations__isnull=False).distinct(),
            "patients": Patient.objects.filter(prestations__isnull=False).distinct(),
            "services": services,
            "now": timezone.now(),
            "start_date": start_date,
            "end_date": end_date,
        }

        return render(request, "prestations/list.html", context)


class PrestationDetailView(View):

    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        actes = prestation.actes_details.select_related(
            "acte", "convention"
        ).prefetch_related("consommations__produit")

        # Initialisation des totaux
        total_actes_espece = Decimal("0.00")
        total_actes_convention = Decimal("0.00")
        total_consommations = Decimal("0.00")

        for pa in actes:
            # Si convention nulle -> paiement en espèces
            if pa.convention is None:
                total_actes_espece += pa.tarif_conventionne
            else:
                total_actes_convention += pa.tarif_conventionne

            # Calcul des consommations supplémentaires
            for conso in pa.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supplementaire = (
                        conso.quantite_reelle - conso.quantite_defaut
                    )
                    total_consommations += quantite_supplementaire * conso.prix_unitaire

        # Calcul des totaux finaux
        total_actes = total_actes_espece + total_actes_convention
        total_espece = (
            total_actes_espece + total_consommations + prestation.prix_supplementaire
        )
        total_general = (
            total_actes_convention + total_espece + prestation.prix_supplementaire
        )
        return render(
            request,
            "prestations/detail.html",
            {
                "prestation": prestation,
                "actes": actes,
                "total_actes": total_actes,
                "total_actes_convention": total_actes_convention,
                "total_actes_espece": total_actes_espece,
                "total_consommations": total_consommations,
                "prix_supplementaire": prestation.prix_supplementaire,
                "total_general": total_general,
                "total_espece": total_espece,
            },
        )


class PrestationUpdateView(View):
    def get(self, request, prestation_id):
        from pharmacies.models import Produit

        # Récupérer la prestation à modifier
        prestation = get_object_or_404(Prestation, id=prestation_id)

        # Vérifier les permissions si nécessaire
        # if not request.user.has_perm('medical.change_prestation'):
        #     return HttpResponseForbidden()

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()

        # Récupère tous les produits actifs pour initialiser le JS
        all_prods = Produit.objects.filter(est_actif=True)

        # Services autorisés par l'utilisateur
        services = services_autorises(request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = Acte.objects.prefetch_related("conventions").filter(
            service__id__in=service_ids
        )
        actes_data = [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(acte.conventions.all().values("id", "nom")),
            }
            for acte in actes
        ]

        # Préparer les données des actes existants
        prestation_actes = []
        for pa in prestation.actes_details.all():
            consommations = [
                {
                    'produit_id': cp.produit.id,
                    'quantite_defaut': cp.quantite_defaut,
                    'quantite_reelle': cp.quantite_reelle,
                    'prix_unitaire': float(cp.prix_unitaire),  # ← convert to float
                }
                for cp in pa.consommations.all()
            ]
            prestation_actes.append({
                'acte_id': pa.acte.id,
                'convention_id': pa.convention.id if pa.convention else None,
                'convention_accordee': pa.convention_accordee,
                'tarif': float(pa.tarif_conventionne),        # ← convert to float
                'consommations': consommations,
            })

        # Prépare le contexte
        context = {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": Prestation.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "prestation_actes_json": json.dumps(prestation_actes),
            # Pour la gestion dynamique des produits
            "all_produits": all_prods,
            "all_produits_json": json.dumps([
                { **prod, "prix_vente": float(prod["prix_vente"]) }
                for prod in all_prods.values("id", "code_produit", "nom", "prix_vente")
            ]),
        }

        return render(request, "prestations/update.html", context)

    @transaction.atomic
    def post(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, id=prestation_id)

        errors = []
        # Champs obligatoires
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        date_str = request.POST.get("date_prestation")
        statut = request.POST.get("statut")
        observations = request.POST.get("observations", "").strip()

        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        conv_ok_vals = request.POST.getlist("convention_accordee[]")

        if not (patient_id and medecin_id and date_str and statut):
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Conversion de la date
        try:
            date_prest = timezone.datetime.strptime(date_str, "%Y-%m-%d")
            # Make it timezone-aware
            if timezone.is_naive(date_prest):
                date_prest = timezone.make_aware(date_prest)
        except (ValueError, TypeError):
            errors.append("Format de date invalide.")

        prestation_data = []
        conso_data = []
        total = Decimal("0.00")

        # Validation des actes
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = Acte.objects.get(pk=acte_pk)
                conv = None
                conv_ok = False
                if convention_ids and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    conv_ok = conv_ok_vals[idx] == "oui"

                tarif = Decimal(tarifs[idx] or "0")
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                    }
                )

                # Récupération des consommations par acte
                prod_field = f"actes[{idx}][produits][]"
                qty_field = f"actes[{idx}][quantites_reelles][]"
                for pid, qty in zip(
                    request.POST.getlist(prod_field), request.POST.getlist(qty_field)
                ):
                    conso_data.append(
                        {
                            "idx": idx,
                            "produit_id": pid,
                            "quantite_reelle": qty,
                        }
                    )

            except Acte.DoesNotExist:
                errors.append(f"Acte invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            # Retourner le formulaire avec les erreurs
            context = self.get_context_data(prestation)
            context['errors'] = errors
            return render(request, "prestations/edit.html", context)

        # Mise à jour de la prestation
        prestation.patient_id = patient_id
        prestation.medecin_id = medecin_id
        prestation.date_prestation = date_prest
        prestation.statut = statut
        prestation.observations = observations
        prestation.prix_total = total
        prestation.prix_supplementaire = Decimal(request.POST.get("prix_supplementaire", "0"))
        prestation.save()

        # Supprimer les anciens actes et consommations
        prestation.actes_details.all().delete()
        # Créer les nouveaux PrestationActe et consommations
        for idx, d in enumerate(prestation_data):
            pa = PrestationActe.objects.create(
                prestation=prestation,
                acte=d["acte"],
                convention=d["convention"],
                convention_accordee=d["convention_accordee"],
                tarif_conventionne=d["tarif"],
            )

            for c in [c for c in conso_data if c["idx"] == idx]:
                if not c["produit_id"] or int(c["quantite_reelle"]) <= 0:
                    continue

                prod = get_object_or_404(Produit, id=c["produit_id"])
                quantite_reelle = int(c["quantite_reelle"])

                try:
                    acte_produit = ActeProduit.objects.get(
                        acte=d["acte"],
                        produit=prod
                    )
                    qte_defaut = acte_produit.quantite_defaut
                except ActeProduit.DoesNotExist:
                    qte_defaut = 0

                ConsommationProduit.objects.create(
                    prestation_acte=pa,
                    produit=prod,
                    quantite_defaut=qte_defaut,
                    quantite_reelle=quantite_reelle,
                    prix_unitaire=prod.prix_vente,
                )

        # Mise à jour du stock
        prestation.update_stock()

        messages.success(request, "Prestation modifiée avec succès.")
        return redirect("medical:prestation_detail", prestation_id=prestation.id)

    def get_context_data(self, prestation):
        """Méthode helper pour récupérer le contexte en cas d'erreur"""
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_actif=True)

        services = services_autorises(self.request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = Acte.objects.prefetch_related("conventions").filter(
            service__id__in=service_ids
        )
        actes_data = [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(acte.conventions.all().values("id", "nom")),
            }
            for acte in actes
        ]

        return {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": Prestation.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "all_produits": all_prods,
            "all_produits_json": json.dumps([
                { **prod, "prix_vente": float(prod["prix_vente"]) }
                for prod in all_prods.values("id", "code_produit", "nom", "prix_vente")
            ]),
        }


class PrestationDeleteView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        return render(
            request,
            "prestations/confirm_delete.html",
            {"prestation": prestation},
        )

    def post(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        prestation.delete()
        return redirect("medical:prestation_list")


class PatientPrestationHistoryView(View):
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, pk=patient_id)
        prestations = Prestation.objects.filter(patient=patient).order_by(
            "-date_prestation"
        )[
            :10
        ]  # Dernières 10 prestations

        data = {
            "patient": patient.nom_complet,
            "prestations": [
                {
                    "id": p.id,
                    "date": p.date_prestation.strftime("%d/%m/%Y"),
                    "medecin": p.medecin.nom_complet,
                    "statut": p.get_statut_display(),
                    "total": float(p.prix_total),
                    "actes": [
                        {
                            "libelle": pa.acte.libelle,
                            "tarif": float(pa.tarif_conventionne),
                        }
                        for pa in p.actes_details.all()
                    ],
                }
                for p in prestations
            ],
        }
        return JsonResponse(data)
