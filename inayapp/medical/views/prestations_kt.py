# Dans views.py - Ajouter cette nouvelle vue pour le changement de statut
import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models, transaction
from django.db.models import ExpressionWrapper, F, Prefetch, Q, Sum, Value
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from medecin.models import Medecin
from medical.models import ActeKt, ActeProduit, PrestationActe, PrestationKt
from medical.models.prestation_Kt import \
    TarifActe  # Plus besoin de TarifActeConvention
from medical.models.prestation_Kt import (ActeProduit, Convention,
                                          PrixSupplementaireConfig)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from patients.models import Patient
from pharmacies.models import ConsommationProduit, Produit
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from utils.utils import services_autorises
from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator


@method_decorator(
    permission_required("medical.view_tarifs_acte", raise_exception=True),
    name="dispatch",
)
class GetTarifView(View):
    """Vue simplifiée pour récupérer les tarifs"""
    def get(self, request):
        acte_id = request.GET.get("acte_id")
        convention_id = request.GET.get("convention_id")
        tarif = Decimal("0.00")

        try:
            acte = ActeKt.objects.get(pk=acte_id)

            # Recherche du tarif approprié
            if convention_id:
                # Tarif avec convention
                convention = Convention.objects.get(pk=convention_id)
                tarif_obj = TarifActe.objects.filter(
                    acte=acte,
                    convention=convention
                ).order_by("-date_effective").first()
            else:
                # Tarif de base (sans convention)
                tarif_obj = TarifActe.objects.filter(
                    acte=acte,
                    convention__isnull=True
                ).order_by("-is_default", "-date_effective").first()

            if tarif_obj:
                tarif = tarif_obj.montant

            return JsonResponse({"tarif": float(tarif)})

        except ActeKt.DoesNotExist:
            return JsonResponse({"error": "ActeKt introuvable"}, status=404)
        except Convention.DoesNotExist:
            return JsonResponse({"error": "Convention introuvable"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@method_decorator(
    permission_required("medical.view_produits_acte", raise_exception=True),
    name="dispatch",
)
class GetActeProduitsView(View):
    def get(self, request, acte_id):
        acte = get_object_or_404(ActeKt, id=acte_id)
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


@method_decorator(
    permission_required("medical.add_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationCreateView(View):
    def get(self, request):
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_active=True)

        # Services autorisés par l'utilisateur
        services = services_autorises(request.user)
        if not services:
            messages.error(
                request,
                "Vous n'êtes assigné à aucun service. Contactez l'administrateur.",
            )
            return redirect("medical:prestation_list")

        service_ids = list(services.values_list("id", flat=True))

        # Récupération des actes avec leurs conventions disponibles
        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            # Récupération des conventions pour cet acte
            conventions_acte = Convention.objects.filter(
                tarifs_acte__acte=acte,
                active=True
            ).distinct().values("id", "nom")

            actes_data.append({
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(conventions_acte),
            })

        context = {
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "now": timezone.localdate(),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
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
        dossier_complet_vals = request.POST.getlist("dossier_convention_complet[]")

        if not (patient_id and medecin_id and date_str and statut):
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Conversion de la date
        try:
            date_prest = timezone.datetime.strptime(date_str, "%Y-%m-%d")
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
                acte = ActeKt.objects.get(pk=acte_pk)
                conv = None
                conv_ok = False
                dossier_complet = False

                if convention_ids and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    conv_ok = conv_ok_vals[idx] == "oui"
                    # NOUVEAU : gestion du dossier complet
                    dossier_complet = dossier_complet_vals[idx] == "oui"

                tarif = Decimal(tarifs[idx] or "0")
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                    "dossier_convention_complet": dossier_complet,  # NOUVEAU
                })

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

            except ActeKt.DoesNotExist:
                errors.append(f"ActeKt invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            # Retourner avec les erreurs
            context = self._get_context_data()
            context["errors"] = errors
            return render(request, "prestations/create.html", context)

        # Calculer la part du médecin supplementaire
        try:
            medecin = Medecin.objects.get(id=medecin_id)
            config = PrixSupplementaireConfig.objects.get(medecin=medecin)
            pourcentage_medecin = config.pourcentage
        except (Medecin.DoesNotExist, PrixSupplementaireConfig.DoesNotExist):
            pourcentage_medecin = Decimal("0.00")

        prix_supplementaire_total = Decimal(
            request.POST.get("prix_supplementaire", "0")
        )
        part_medecin = prix_supplementaire_total * pourcentage_medecin / 100

        # Création de la prestation
        prestation = PrestationKt.objects.create(
            patient_id=patient_id,
            medecin_id=medecin_id,
            date_prestation=date_prest,
            statut=statut,
            observations=observations,
            prix_total=total,
            prix_supplementaire=prix_supplementaire_total,
            prix_supplementaire_medecin=part_medecin,
        )

        # Création des PrestationActe et consommations
        for idx, d in enumerate(prestation_data):
            pa = PrestationActe.objects.create(
                prestation=prestation,
                acte=d["acte"],
                convention=d["convention"],
                convention_accordee=d["convention_accordee"],
                dossier_convention_complet=d["dossier_convention_complet"],  # NOUVEAU
                tarif_conventionne=d["tarif"],
            )

            # Traitement des consommations
            for c in [c for c in conso_data if c["idx"] == idx]:
                if not c["produit_id"] or int(c["quantite_reelle"]) <= 0:
                    continue

                prod = get_object_or_404(Produit, id=c["produit_id"])
                quantite_reelle = int(c["quantite_reelle"])

                # Récupération de la quantité par défaut
                try:
                    acte_produit = ActeProduit.objects.get(acte=d["acte"], produit=prod)
                    qte_defaut = acte_produit.quantite_defaut
                except ActeProduit.DoesNotExist:
                    qte_defaut = 0

                # Création de la consommation
                ConsommationProduit.objects.create(
                    prestation_acte=pa,
                    produit=prod,
                    quantite_defaut=qte_defaut,
                    quantite_reelle=quantite_reelle,
                    prix_unitaire=prod.prix_vente,
                )

        messages.success(request, "Prestation créée avec succès.")
        return redirect("medical:prestation_detail", prestation_id=prestation.id)

    def _get_context_data(self):
        """Méthode helper pour récupérer le contexte en cas d'erreur"""
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_active=True)

        services = services_autorises(self.request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            conventions_acte = Convention.objects.filter(
                tarifs_acte__acte=acte,
                active=True
            ).distinct().values("id", "nom")

            actes_data.append({
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(conventions_acte),
            })

        return {
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "now": timezone.localdate(),
            "all_produits": all_prods,
            "all_produits_json": json.dumps([
                {**prod, "prix_vente": float(prod["prix_vente"])}
                for prod in all_prods.values("id", "code_produit", "nom", "prix_vente")
            ]),
        }


@method_decorator(
    permission_required("medical.planifier_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationProgrammerView(View):
    """Vue pour programmer des prestations (statut PLANIFIE) - Version simplifiée"""

    def get(self, request):
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_active=True)

        # Services autorisés par l'utilisateur
        services = services_autorises(request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            # Récupération simplifiée des conventions
            conventions_acte = Convention.objects.filter(
                tarifs_acte__acte=acte,
                active=True
            ).distinct().values("id", "nom")

            actes_data.append({
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(conventions_acte),
            })

        context = {
            "patients": patients,
            "medecins": medecins,
            "actes_json": json.dumps(actes_data),
            "now": timezone.localdate(),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
        }

        return render(request, "prestations/schedule.html", context)

    @transaction.atomic
    def post(self, request):
        errors = []

        # Champs obligatoires
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        date_str = request.POST.get("date_prestation")
        heure_str = request.POST.get("heure_prestation", "08:00")
        observations = request.POST.get("observations", "").strip()

        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        conv_ok_vals = request.POST.getlist("convention_accordee[]")

        if not (patient_id and medecin_id and date_str):
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Conversion de la date et heure
        try:
            date_prest = timezone.datetime.strptime(
                f"{date_str} {heure_str}", "%Y-%m-%d %H:%M"
            )
            if timezone.is_naive(date_prest):
                date_prest = timezone.make_aware(date_prest)

            # Vérifier que la date est future
            if date_prest <= timezone.now():
                errors.append("La date de programmation doit être dans le futur.")

        except (ValueError, TypeError):
            errors.append("Format de date ou d'heure invalide.")

        prestation_data = []
        total = Decimal("0.00")

        # Validation des actes avec la logique simplifiée
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = ActeKt.objects.get(pk=acte_pk)
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

            except ActeKt.DoesNotExist:
                errors.append(f"ActeKt invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            return render(
                request,
                "prestations/schedule.html",
                {
                    "errors": errors,
                    "patients": Patient.objects.all(),
                    "medecins": Medecin.objects.all(),
                    "actes_json": json.dumps([]),
                    "now": timezone.localdate(),
            })

        # Création de la prestation programmée
        prestation = PrestationKt.objects.create(
            patient_id=patient_id,
            medecin_id=medecin_id,
            date_prestation=date_prest,
            statut="PLANIFIE",
            observations=observations,
            prix_total=total,
        )

        # Création des PrestationActe (sans consommations pour une prestation planifiée)
        for d in prestation_data:
            PrestationActe.objects.create(
                prestation=prestation,
                acte=d["acte"],
                convention=d["convention"],
                convention_accordee=d["convention_accordee"],
                tarif_conventionne=d["tarif"],
            )

        messages.success(
            request,
            f"Prestation programmée avec succès pour le {date_prest.strftime('%d/%m/%Y à %H:%M')}",
        )
        return redirect("medical:prestation_detail", prestation_id=prestation.id)


@method_decorator(
    permission_required("medical.view_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationListView(View):
    def get(self, request):
        from accueil.models import ConfigDate

        # Configuration des dates
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

        start_date, end_date = config.start_date, config.end_date

        # Services autorisés
        services = services_autorises(request.user)
        service_ids = services.values_list("id", flat=True)

        # Filtrage des prestations
        prestations = (
            PrestationKt.objects.filter(actes__service__id__in=service_ids)
            .select_related("patient", "medecin")
            .prefetch_related(
                "actes_details__acte",
                "actes_details__consommations__produit"
            )
            .annotate(
                total_calcule=ExpressionWrapper(
                    F('prix_total') + F('prix_supplementaire'),
                    output_field=models.DecimalField(max_digits=10, decimal_places=2)
                )
            )
            .order_by("-date_prestation")
            .distinct()
        )

        # Application des filtres
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

            if param == "service":
                sid = caster(val)
                if sid not in service_ids:
                    prestations = prestations.none()
                    break
                prestations = prestations.filter(**{field: sid})
                continue

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

        # Pagination
        items_per_page = min(max(int(request.GET.get("per_page", 25)), 10), 100)
        paginator = Paginator(prestations, items_per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        # Statistiques par statut
        stats_by_status = {}
        for status_code, status_label in PrestationKt.STATUT_CHOICES:
            count = prestations.filter(statut=status_code).count()
            stats_by_status[status_code] = {
                'count': count,
                'label': status_label
            }

        context = {
            "paginator": paginator,
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "items_per_page": items_per_page,
            "total_count": paginator.count,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "medecins": Medecin.objects.filter(prestations__isnull=False).distinct(),
            "patients": Patient.objects.filter(prestations__isnull=False).distinct(),
            "services": services,
            "now": timezone.now(),
            "start_date": start_date,
            "end_date": end_date,
            "stats_by_status": stats_by_status,
        }
        return render(request, "prestations/list.html", context)


@method_decorator(
    permission_required("medical.view_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationDetailView(View):
    """Vue détail optimisée"""
    def get(self, request, prestation_id):
        prestation = get_object_or_404(
            PrestationKt.objects.select_related('patient', 'medecin')
            .prefetch_related(
                Prefetch(
                    'actes_details',
                    queryset=PrestationActe.objects.select_related('acte', 'convention')
                    .prefetch_related(
                        Prefetch(
                            'consommations',
                            queryset=ConsommationProduit.objects.select_related('produit')
                        )
                    )
                )
            ),
            pk=prestation_id
        )

        actes = prestation.actes_details.all()

        # NOUVEAU: Vérifier s'il y a des actes en espèces
        has_actes_especes = (
            actes.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            ).exists()
            or prestation.prix_supplementaire
        )

        # Calculs des totaux
        total_actes_espece = Decimal("0.00")
        total_actes_convention = Decimal("0.00")
        total_consommations = Decimal("0.00")

        for pa in actes:
            if pa.convention is None or (pa.convention and pa.convention.nom.lower() == "urgence"):
                total_actes_espece += pa.tarif_conventionne
            else:
                total_actes_convention += pa.tarif_conventionne

            # Calcul des consommations supplémentaires
            for conso in pa.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supplementaire = conso.quantite_reelle - conso.quantite_defaut
                    total_consommations += quantite_supplementaire * conso.prix_unitaire

        # Totaux finaux
        total_actes = total_actes_espece + total_actes_convention
        total_espece = (
            total_actes_espece + total_consommations + prestation.prix_supplementaire
        )
        total_general = total_actes + total_consommations + prestation.prix_supplementaire
        total_convention = total_actes_convention

        return render(
            request,
            "prestations/detail.html",
            {
                "prestation": prestation,
                "actes": actes,
                "has_actes_especes": has_actes_especes,  # NOUVEAU
                "total_actes": total_actes,
                "total_actes_convention": total_actes_convention,
                "total_actes_espece": total_actes_espece,
                "total_consommations": total_consommations,
                "prix_supplementaire": prestation.prix_supplementaire,
                "total_general": total_general,
                "total_espece": total_espece,
                "total_convention": total_convention,
            }
        )


@method_decorator(
    permission_required("medical.change_status_prestationkt", raise_exception=True),
    name="dispatch",
)
@method_decorator(csrf_exempt, name="dispatch")
class PrestationChangeStatusView(View):
    """Vue pour changer le statut d'une prestation via AJAX"""

    def post(self, request, prestation_id):
        try:
            prestation = get_object_or_404(PrestationKt, id=prestation_id)
            # Parse JSON data
            data = json.loads(request.body)
            new_status = data.get('status')
            # Vérifications spécifiques par statut
            if new_status == "REALISE" and not request.user.has_perm(
                "medical.realiser_prestationkt"
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Permission insuffisante pour marquer comme réalisé",
                    }
                )

            if new_status == "PAYE" and not request.user.has_perm(
                "medical.payer_prestationkt"
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Permission insuffisante pour marquer comme payé",
                    }
                )

            if new_status == "ANNULE" and not request.user.has_perm(
                "medical.annuler_prestationkt"
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Permission insuffisante pour annuler",
                    }
                )
            # Validation du nouveau statut
            valid_statuses = ['PLANIFIE', 'REALISE', 'PAYE', 'ANNULE']
            if new_status not in valid_statuses:
                return JsonResponse({
                    'success': False,
                    'message': 'Statut invalide'
                })

            # Validation des transitions autorisées
            valid_transitions = {
                'PLANIFIE': ['REALISE', 'ANNULE'],
                'REALISE': ['PAYE'],
                'PAYE': [],  # Aucune transition depuis PAYE
                'ANNULE': []  # Aucune transition depuis ANNULE
            }

            if new_status not in valid_transitions.get(prestation.statut, []):
                return JsonResponse({
                    'success': False,
                    'message': f'Transition de {prestation.get_statut_display()} vers {dict(PrestationKt.STATUT_CHOICES)[new_status]} non autorisée'
                })

            # Mettre à jour le statut
            prestation.statut = new_status
            prestation.save(update_fields=['statut'])

            return JsonResponse({
                'success': True,
                'message': f'Statut mis à jour vers {prestation.get_statut_display()}'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })


@method_decorator(
    permission_required("medical.change_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationUpdateView(View):
    """Vue de modification simplifiée"""

    def get(self, request, prestation_id):
        from pharmacies.models import Produit

        prestation = get_object_or_404(PrestationKt, id=prestation_id)

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_active=True)

        services = services_autorises(request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            conventions_acte = (
                Convention.objects.filter(tarifs_acte__acte=acte, active=True)
                .distinct()
                .values("id", "nom")
            )

            actes_data.append(
                {
                    "id": acte.id,
                    "code": acte.code,
                    "libelle": acte.libelle,
                    "conventions": list(conventions_acte),
                }
            )

        # Préparer les données des actes existants
        prestation_actes = []
        for pa in prestation.actes_details.all():
            consommations = [
                {
                    "produit_id": cp.produit.id,
                    "quantite_defaut": cp.quantite_defaut,
                    "quantite_reelle": cp.quantite_reelle,
                    "prix_unitaire": float(cp.prix_unitaire),
                }
                for cp in pa.consommations.all()
            ]
            prestation_actes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else None,
                    "convention_accordee": pa.convention_accordee,
                    "dossier_convention_complet": pa.dossier_convention_complet,  # NOUVEAU
                    "tarif": float(pa.tarif_conventionne),
                    "consommations": consommations,
                }
            )

        context = {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "prestation_actes_json": json.dumps(prestation_actes),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
        }

        return render(request, "prestations/update.html", context)

    def _get_context_data(self, prestation):
        """Méthode helper pour récupérer le contexte en cas d'erreur"""
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_active=True)

        services = services_autorises(self.request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            conventions_acte = (
                Convention.objects.filter(tarifs_acte__acte=acte, active=True)
                .distinct()
                .values("id", "nom")
            )

            actes_data.append(
                {
                    "id": acte.id,
                    "code": acte.code,
                    "libelle": acte.libelle,
                    "conventions": list(conventions_acte),
                }
            )

        # Préparer les données des actes existants
        prestation_actes = []
        for pa in prestation.actes_details.all():
            consommations = [
                {
                    "produit_id": cp.produit.id,
                    "quantite_defaut": cp.quantite_defaut,
                    "quantite_reelle": cp.quantite_reelle,
                    "prix_unitaire": float(cp.prix_unitaire),
                }
                for cp in pa.consommations.all()
            ]
            prestation_actes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else None,
                    "convention_accordee": pa.convention_accordee,
                    "dossier_convention_complet": pa.dossier_convention_complet,  # NOUVEAU
                    "tarif": float(pa.tarif_conventionne),
                    "consommations": consommations,
                }
            )

        return {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "prestation_actes_json": json.dumps(prestation_actes),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
        }

    @transaction.atomic
    def post(self, request, prestation_id):
        prestation = get_object_or_404(PrestationKt, id=prestation_id)

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
        dossier_complet_vals = request.POST.getlist("dossier_convention_complet[]")

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
                acte = ActeKt.objects.get(pk=acte_pk)
                conv = None
                conv_ok = False
                dossier_complet = False

                if convention_ids and idx < len(convention_ids) and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    if idx < len(conv_ok_vals):
                        conv_ok = conv_ok_vals[idx] == "oui"
                    if idx < len(dossier_complet_vals):
                        dossier_complet = dossier_complet_vals[idx] == "oui"

                tarif = (
                    Decimal(tarifs[idx] or "0") if idx < len(tarifs) else Decimal("0")
                )
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                        "dossier_convention_complet": dossier_complet,
                    }
                )

                # Récupération des consommations par acte (pour facturation uniquement)
                prod_field = f"actes[{idx}][produits][]"
                qty_field = f"actes[{idx}][quantites_reelles][]"
                for pid, qty in zip(
                    request.POST.getlist(prod_field), request.POST.getlist(qty_field)
                ):
                    if pid and qty:  # Vérifier que les valeurs ne sont pas vides
                        conso_data.append(
                            {
                                "idx": idx,
                                "produit_id": pid,
                                "quantite_reelle": qty,
                            }
                        )

            except ActeKt.DoesNotExist:
                errors.append(f"ActeKt invalide à la ligne {idx+1}.")
            except Convention.DoesNotExist:
                errors.append(f"Convention invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            # Retourner le formulaire avec les erreurs en utilisant la méthode helper
            context = self._get_context_data(prestation)
            context["errors"] = errors
            return render(request, "prestations/update.html", context)

        # Récupérer les nouveaux objets
        nouveau_prix_supplementaire = Decimal(
            request.POST.get("prix_supplementaire", "0")
        )

        # Mise à jour de la prestation
        prestation.patient_id = patient_id
        prestation.medecin_id = medecin_id
        prestation.date_prestation = date_prest
        prestation.statut = statut
        prestation.observations = observations
        prestation.prix_total = total
        prestation.prix_supplementaire = nouveau_prix_supplementaire
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
                dossier_convention_complet=d["dossier_convention_complet"],
                tarif_conventionne=d["tarif"],
            )

            # Traitement des consommations (pour facturation uniquement)
            for c in [c for c in conso_data if c["idx"] == idx]:
                if not c["produit_id"] or int(c["quantite_reelle"]) <= 0:
                    continue

                try:
                    prod = get_object_or_404(Produit, id=c["produit_id"])
                    quantite_reelle = int(c["quantite_reelle"])

                    try:
                        acte_produit = ActeProduit.objects.get(
                            acte=d["acte"], produit=prod
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
                except Exception as e:
                    # Log l'erreur mais continuez le traitement
                    print(f"Erreur lors de la création de la consommation: {e}")

        messages.success(request, "Prestation modifiée avec succès.")
        return redirect("medical:prestation_detail", prestation_id=prestation.id)


@method_decorator(
    permission_required("medical.delete_prestationkt", raise_exception=True),
    name="dispatch",
)
class PrestationDeleteView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(PrestationKt, pk=prestation_id)
        return render(request, "prestations/confirm_delete.html", {
            "prestation": prestation
        })

    @transaction.atomic
    def post(self, request, prestation_id):
        prestation = get_object_or_404(PrestationKt, pk=prestation_id)

        # Supprimer la prestation (plus besoin de gérer le stock)
        prestation.delete()

        messages.success(request, "Prestation supprimée avec succès.")
        return redirect("medical:prestation_list")


@method_decorator(
    permission_required("medical.view_patient_history", raise_exception=True),
    name="dispatch",
)
class PatientPrestationHistoryView(View):
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, pk=patient_id)
        prestations = (
            PrestationKt.objects.filter(patient=patient)
            .exclude(statut="PLANIFIE")
            .order_by("-date_prestation")
        )

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


import io
from datetime import datetime
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.db.models import Prefetch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from medical.models import PrestationKt, PrestationActe
from pharmacies.models import ConsommationProduit
from utils.utils import services_autorises


@method_decorator(
    permission_required("medical.export_prestationkt", raise_exception=True),
    name="dispatch",
)
class ExportPrestationsPdfView(View):
    """Vue pour exporter les prestations planifiées en PDF avec un design optimisé"""

    def post(self, request):
        try:
            # Récupération de la date depuis le formulaire
            export_date_str = request.POST.get("export_date")

            if not export_date_str:
                messages.error(request, "Date d'exportation manquante")
                return redirect("medical:prestation_list")

            # Convertir la date
            try:
                export_date = datetime.strptime(export_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Format de date invalide")
                return redirect("medical:prestation_list")

            # Services autorisés pour l'utilisateur
            services = services_autorises(request.user)
            service_ids = services.values_list("id", flat=True)

            # Récupérer les prestations planifiées pour cette date
            prestations = (
                PrestationKt.objects.filter(
                    actes_details__acte__service__id__in=service_ids,
                    statut="PLANIFIE",
                    date_prestation__date=export_date,
                )
                .select_related("patient", "medecin")
                .prefetch_related(
                    Prefetch(
                        "actes_details",
                        queryset=PrestationActe.objects.select_related(
                            "acte", "convention"
                        ).prefetch_related(
                            Prefetch(
                                "consommations",
                                queryset=ConsommationProduit.objects.select_related(
                                    "produit"
                                ),
                            )
                        ),
                    )
                )
                .distinct()
                .order_by(
                    "date_prestation", "patient__last_name", "patient__first_name"
                )
            )

            # Vérifier s'il y a des prestations
            if not prestations.exists():
                messages.warning(
                    request,
                    f"Aucune prestation planifiée trouvée pour le {export_date.strftime('%d/%m/%Y')}",
                )
                return redirect("medical:prestation_list")

            # Générer le PDF
            return self._generate_pdf(prestations, export_date, request.user)

        except Exception as e:
            messages.error(request, f"Erreur lors de l'exportation : {str(e)}")
            return redirect("medical:prestation_list")

    def _generate_pdf(self, prestations, export_date, user):
        """Génère le fichier PDF avec un design optimisé pour la lisibilité"""

        # Configuration de la réponse HTTP
        response = HttpResponse(content_type="application/pdf")
        filename = f"planning_prestations_{export_date.strftime('%Y-%m-%d')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # Création du document PDF avec marges optimisées
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )

        # Styles personnalisés
        styles = getSampleStyleSheet()

        # Style pour l'en-tête principal
        header_style = ParagraphStyle(
            "CustomHeader",
            parent=styles["Normal"],
            fontSize=16,
            fontName="Helvetica-Bold",
            spaceAfter=12,
            alignment=1,
            textColor=colors.HexColor("#1e3a8a"),
        )

        # Style pour les sous-titres
        subheader_style = ParagraphStyle(
            "SubHeader",
            parent=styles["Normal"],
            fontSize=12,
            fontName="Helvetica-Bold",
            spaceAfter=6,
            alignment=1,
            textColor=colors.HexColor("#374151"),
        )

        # Style pour les statistiques
        stats_style = ParagraphStyle(
            "StatsStyle",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica",
            spaceAfter=10,
            alignment=1,
            textColor=colors.HexColor("#374151"),
        )

        # Style pour les cellules du tableau
        cell_style = ParagraphStyle(
            "CellStyle",
            parent=styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )

        # Style pour les en-têtes de tableau
        header_cell_style = ParagraphStyle(
            "HeaderCellStyle",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            leading=12,
            spaceAfter=0,
            spaceBefore=0,
            textColor=colors.white,
        )

        # Contenu du document
        story = []

        # En-tête principal
        story.append(Paragraph("Planning des Prestations KT", header_style))

        # Formatage de la date en français
        mois_fr = {
            1: "janvier",
            2: "février",
            3: "mars",
            4: "avril",
            5: "mai",
            6: "juin",
            7: "juillet",
            8: "août",
            9: "septembre",
            10: "octobre",
            11: "novembre",
            12: "décembre",
        }

        jour_fr = {
            0: "lundi",
            1: "mardi",
            2: "mercredi",
            3: "jeudi",
            4: "vendredi",
            5: "samedi",
            6: "dimanche",
        }

        jour_nom = jour_fr[export_date.weekday()]
        mois_nom = mois_fr[export_date.month]
        date_formatee = (
            f"{jour_nom.title()} {export_date.day} {mois_nom} {export_date.year}"
        )

        story.append(Paragraph(date_formatee, subheader_style))
        story.append(Spacer(1, 15))

        # Statistiques
        total_prestations = prestations.count()
        actes_details = PrestationActe.objects.filter(prestation__in=prestations)

        # Actes conventionnés (excluant urgence)
        actes_conventionnes_qs = actes_details.filter(convention__isnull=False).exclude(
            convention__nom__iexact="urgence"
        )

        # Actes non conventionnés (sans convention ou urgence)
        actes_non_conventionnes_qs = actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )

        # Compter les totaux
        actes_conventionnes = actes_conventionnes_qs.count()
        actes_non_conventionnes = actes_non_conventionnes_qs.count()

        # Compter les actes avec problèmes
        actes_sans_accord = actes_conventionnes_qs.filter(
            convention_accordee=False
        ).count()
        actes_sans_dossier_complet = actes_conventionnes_qs.filter(
            dossier_convention_complet=False
        ).count()

        # Tableau de statistiques
        stats_data = [
            ["Total des prestations", str(total_prestations)],
            ["Actes conventionnés", str(actes_conventionnes)],
            ["Actes non conventionnés", str(actes_non_conventionnes)],
            ["Actes sans accord", str(actes_sans_accord)],
            ["Actes sans dossier complet", str(actes_sans_dossier_complet)],
        ]

        stats_table = Table(stats_data, colWidths=[3.5 * inch, 1.5 * inch])
        stats_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e5e7eb")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.black),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(stats_table)
        story.append(Spacer(1, 20))

        # Préparation des données du tableau principal
        data = []

        # En-têtes du tableau
        headers = [
            Paragraph("<b>Patient</b>", header_cell_style),
            Paragraph("<b>Médecin</b>", header_cell_style),
            Paragraph("<b>Actes</b>", header_cell_style),
            Paragraph("<b>Convention</b>", header_cell_style),
            Paragraph("<b>Accord</b>", header_cell_style),
            Paragraph("<b>Dossier</b>", header_cell_style),
        ]
        data.append(headers)

        # Données des prestations
        for prestation in prestations:
            # Nom complet du patient
            patient_first = prestation.patient.first_name or ""
            patient_last = prestation.patient.last_name or ""
            patient_nom = f"{patient_first} {patient_last}".strip()
            if not patient_nom:
                patient_nom = "Patient Inconnu"

            # Nom complet du médecin
            medecin_first = prestation.medecin.first_name or ""
            medecin_last = prestation.medecin.last_name or ""
            medecin_nom = f"Dr. {medecin_first} {medecin_last}".strip()
            if not medecin_nom or medecin_nom == "Dr. ":
                medecin_nom = "Dr. Inconnu"

            # Liste des actes
            actes_list = []
            for pa in prestation.actes_details.all():
                libelle = pa.acte.libelle
                acte_info = f"• {pa.acte.code} - {libelle}"
                actes_list.append(acte_info)

            actes_text = "<br/>".join(actes_list) if actes_list else "Aucun acte"

            # Liste des conventions
            conv_list = []
            for pa in prestation.actes_details.all():
                if pa.convention:
                    conv_name = pa.convention.nom
                    if conv_name.lower() != "urgence":
                        conv_info = f"{conv_name}"
                    else:
                        conv_info = "Urgence"
                else:
                    conv_info = "Non conventionné"
                conv_list.append(conv_info)

            conv_text = "<br/>".join(conv_list) if conv_list else "Aucune convention"

            # Statuts avec couleurs
            convention_accordee = prestation.actes_details.filter(
                convention_accordee=True
            ).exists()
            dossier_complet = prestation.actes_details.filter(
                dossier_convention_complet=True
            ).exists()

            convention_status = "✓" if convention_accordee else "✗"
            dossier_status = "✓" if dossier_complet else "✗"

            # Ligne de données
            row = [
                Paragraph(patient_nom, cell_style),
                Paragraph(medecin_nom, cell_style),
                Paragraph(actes_text, cell_style),
                Paragraph(conv_text, cell_style),
                Paragraph(convention_status, cell_style),
                Paragraph(dossier_status, cell_style),
            ]
            data.append(row)

        # Configuration du tableau principal
        table = Table(
            data,
            colWidths=[
                1.5 * inch,  # Patient
                1.5 * inch,  # Médecin
                2.0 * inch,  # Actes
                1.5 * inch,  # Convention
                0.6 * inch,  # Convention Accordée
                0.6 * inch,  # Dossier Complet
            ],
            repeatRows=1,  # Répéter l'en-tête sur chaque page
        )

        # Style du tableau
        table.setStyle(
            TableStyle(
                [
                    # En-tête
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    # Corps du tableau
                    ("ALIGN", (4, 1), (5, -1), "CENTER"),  # Statuts centrés
                    ("VALIGN", (0, 1), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1e40af")),
                    # Alternance de couleurs des lignes
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f9fafb")],
                    ),
                    # Espacement
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        story.append(table)
        story.append(Spacer(1, 20))

        # Footer avec informations d'export
        user_name = f"{user.first_name} {user.last_name}".strip() or user.username
        footer_text = f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} par {user_name}"
        story.append(Paragraph(footer_text, styles["Normal"]))
        story.append(
            Paragraph(
                "Ce document est confidentiel et destiné à un usage interne uniquement",
                styles["Italic"],
            )
        )

        # Construction du document avec gestion des pages
        def add_page_number(canvas, doc):
            """Ajoute le numéro de page"""
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#6b7280"))
            page_num = canvas.getPageNumber()
            text = f"Page {page_num}"
            canvas.drawRightString(7.5 * inch, 0.5 * inch, text)
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

        # Récupération et envoi du contenu PDF
        pdf_content = buffer.getvalue()
        buffer.close()
        response.write(pdf_content)
        return response


@method_decorator(
    permission_required("medical.generate_bon_paiement", raise_exception=True),
    name="dispatch",
)
class ExportBonPaiementEspecesView(View):
    """Vue pour exporter un bon de paiement espèces en PDF"""

    def get(self, request, prestation_id):
        try:
            # Récupérer la prestation avec optimisations
            prestation = get_object_or_404(
                PrestationKt.objects.select_related(
                    "patient", "medecin"
                ).prefetch_related(
                    Prefetch(
                        "actes_details",
                        queryset=PrestationActe.objects.select_related(
                            "acte", "convention"
                        ).prefetch_related(
                            Prefetch(
                                "consommations",
                                queryset=ConsommationProduit.objects.select_related(
                                    "produit"
                                ),
                            )
                        ),
                    )
                ),
                pk=prestation_id,
            )

            # Filtrer les actes en espèces (sans convention OU urgence)
            actes_especes = prestation.actes_details.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            )

            # Vérifier qu'il y a des actes en espèces OU des frais supplémentaires
            has_actes_especes = actes_especes.exists()
            has_frais_supplementaires = prestation.prix_supplementaire > Decimal("0")

            # Vérifier les consommations supplémentaires
            has_consommations_supplementaires = False
            for acte_detail in prestation.actes_details.all():
                for conso in acte_detail.consommations.all():
                    if conso.quantite_reelle > conso.quantite_defaut:
                        has_consommations_supplementaires = True
                        break
                if has_consommations_supplementaires:
                    break

            # Vérifier qu'il y a au moins quelque chose à payer en espèces
            if not (
                has_actes_especes
                or has_frais_supplementaires
                or has_consommations_supplementaires
            ):
                messages.warning(
                    request,
                    "Cette prestation ne contient aucun élément payable en espèces.",
                )
                return redirect(
                    "medical:prestation_detail", prestation_id=prestation.id
                )

            # Générer le PDF
            return self._generate_bon_paiement_pdf(
                prestation, actes_especes, request.user
            )

        except Exception as e:
            messages.error(
                request, f"Erreur lors de la génération du bon de paiement : {str(e)}"
            )
            return redirect("medical:prestation_detail", prestation_id=prestation_id)

    def _generate_bon_paiement_pdf(self, prestation, actes_especes, user):
        """Génère le bon de paiement en PDF"""

        # Configuration de la réponse HTTP
        response = HttpResponse(content_type="application/pdf")
        filename = f"bon_paiement_especes_{prestation.id}_{prestation.date_prestation.strftime('%Y%m%d')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # Création du document PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        # Styles personnalisés
        styles = getSampleStyleSheet()

        # Style pour l'en-tête principal
        header_style = ParagraphStyle(
            "HeaderStyle",
            parent=styles["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            spaceAfter=20,
            alignment=1,  # Centré
            textColor=colors.HexColor("#1e3a8a"),
        )

        # Style pour les informations
        info_style = ParagraphStyle(
            "InfoStyle",
            parent=styles["Normal"],
            fontSize=11,
            fontName="Helvetica",
            spaceAfter=8,
            textColor=colors.HexColor("#374151"),
        )

        # Style pour les totaux
        total_style = ParagraphStyle(
            "TotalStyle",
            parent=styles["Normal"],
            fontSize=14,
            fontName="Helvetica-Bold",
            spaceAfter=10,
            textColor=colors.HexColor("#059669"),
        )

        # Style pour les cellules
        cell_style = ParagraphStyle(
            "CellStyle",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica",
            leading=12,
        )

        # Contenu du document
        story = []

        # En-tête principal
        story.append(Paragraph("BON DE PAIEMENT ESPÈCES", header_style))
        story.append(Spacer(1, 10))

        # Informations de la prestation
        info_data = [
            ["Numéro de prestation:", f"#{prestation.id}"],
            ["Date:", prestation.date_prestation.strftime("%d/%m/%Y à %H:%M")],
            ["Patient:", prestation.patient.nom_complet],
            ["Médecin:", f"Dr. {prestation.medecin.nom_complet}"],
            ["Statut:", prestation.get_statut_display()],
        ]

        info_table = Table(info_data, colWidths=[2.5 * inch, 4 * inch])
        info_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        story.append(info_table)
        story.append(Spacer(1, 20))

        # Titre des détails
        story.append(
            Paragraph(
                "DÉTAIL DES ÉLÉMENTS EN ESPÈCES",
                ParagraphStyle(
                    "SubTitle",
                    parent=styles["Normal"],
                    fontSize=14,
                    fontName="Helvetica-Bold",
                    spaceAfter=15,
                    textColor=colors.HexColor("#374151"),
                ),
            )
        )

        # Tableau des éléments
        elements_data = []

        # En-têtes
        headers = [
            Paragraph("<b>Code</b>", cell_style),
            Paragraph("<b>Libellé</b>", cell_style),
            Paragraph("<b>Type</b>", cell_style),
            Paragraph("<b>Montant</b>", cell_style),
        ]
        elements_data.append(headers)

        # Calculs des totaux
        total_actes_especes = Decimal("0.00")
        total_consommations_supplementaires = Decimal("0.00")

        # Données des actes en espèces
        for acte_detail in actes_especes:
            # Type de paiement
            if (
                acte_detail.convention
                and acte_detail.convention.nom.lower() == "urgence"
            ):
                type_paiement = "Urgence"
            else:
                type_paiement = "Sans convention"

            # Montant de l'acte
            montant_acte = acte_detail.tarif_conventionne
            total_actes_especes += montant_acte

            # Ligne de l'acte
            row = [
                Paragraph(acte_detail.acte.code, cell_style),
                Paragraph(acte_detail.acte.libelle, cell_style),
                Paragraph(type_paiement, cell_style),
                Paragraph(f"{montant_acte:,.2f} DA", cell_style),
            ]
            elements_data.append(row)

        # Consommations supplémentaires pour TOUS les actes (même conventionnés)
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supplementaire = (
                        conso.quantite_reelle - conso.quantite_defaut
                    )
                    montant_conso = quantite_supplementaire * conso.prix_unitaire
                    total_consommations_supplementaires += montant_conso

                    # Ligne de consommation supplémentaire
                    conso_row = [
                        Paragraph(f"+ {conso.produit.code_produit}", cell_style),
                        Paragraph(
                            f"{conso.produit.nom} (qté supp: {quantite_supplementaire})",
                            cell_style,
                        ),
                        Paragraph("Consommation supp.", cell_style),
                        Paragraph(f"{montant_conso:,.2f} DA", cell_style),
                    ]
                    elements_data.append(conso_row)

        # Frais supplémentaires (si applicable)
        frais_supplementaires = prestation.prix_supplementaire
        if frais_supplementaires > 0:
            frais_row = [
                Paragraph("SUPP", cell_style),
                Paragraph("Frais supplémentaires", cell_style),
                Paragraph("Supplément", cell_style),
                Paragraph(f"{frais_supplementaires:,.2f} DA", cell_style),
            ]
            elements_data.append(frais_row)

        # Configuration du tableau des éléments
        elements_table = Table(
            elements_data, colWidths=[1.2 * inch, 3 * inch, 1.5 * inch, 1.5 * inch]
        )
        elements_table.setStyle(
            TableStyle(
                [
                    # En-tête
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    # Corps du tableau
                    ("ALIGN", (3, 1), (3, -1), "RIGHT"),  # Montants alignés à droite
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1e40af")),
                    # Alternance de couleurs
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f9fafb")],
                    ),
                    # Espacement
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        story.append(elements_table)
        story.append(Spacer(1, 20))

        # Tableau des totaux
        totaux_data = []

        if total_actes_especes > 0:
            totaux_data.append(["Sous-total actes:", f"{total_actes_especes:,.2f} DA"])

        if total_consommations_supplementaires > 0:
            totaux_data.append(
                [
                    "Consommations supplémentaires:",
                    f"{total_consommations_supplementaires:,.2f} DA",
                ]
            )

        if frais_supplementaires > 0:
            totaux_data.append(
                ["Frais supplémentaires:", f"{frais_supplementaires:,.2f} DA"]
            )

        # Total général en espèces
        total_general_especes = (
            total_actes_especes
            + total_consommations_supplementaires
            + frais_supplementaires
        )
        totaux_data.append(["", ""])  # Ligne vide pour séparation
        totaux_data.append(
            ["TOTAL À PAYER EN ESPÈCES:", f"{total_general_especes:,.2f} DA"]
        )

        totaux_table = Table(totaux_data, colWidths=[4 * inch, 2.5 * inch])
        totaux_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (0, -2), "Helvetica"),
                    ("FONTNAME", (1, 0), (1, -2), "Helvetica"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -2), 11),
                    ("FONTSIZE", (0, -1), (-1, -1), 14),
                    ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#059669")),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0fdf4")),
                    ("BOX", (0, -1), (-1, -1), 1, colors.HexColor("#059669")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )

        story.append(totaux_table)
        story.append(Spacer(1, 30))

        # Section signature
        signature_data = [
            ["Signature du patient:", "Signature du responsable:"],
            ["", ""],
            ["", ""],
            ["Date: ___/___/______", "Date: ___/___/______"],
        ]

        story.append(Spacer(1, 20))

        # Pied de page
        footer_text = f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} par {user.get_full_name() or user.username}"
        story.append(
            Paragraph(
                footer_text,
                ParagraphStyle(
                    "Footer",
                    parent=styles["Normal"],
                    fontSize=8,
                    fontName="Helvetica-Oblique",
                    alignment=1,
                    textColor=colors.HexColor("#6b7280"),
                ),
            )
        )

        # Notes importantes
        notes_style = ParagraphStyle(
            "Notes",
            parent=styles["Normal"],
            fontSize=8,
            fontName="Helvetica",
            spaceAfter=4,
            textColor=colors.HexColor("#6b7280"),
        )

        story.append(Spacer(1, 10))

        story.append(
            Paragraph("• Document confidentiel - Usage interne uniquement", notes_style)
        )

        # Construction du document
        def add_page_number(canvas, doc):
            """Ajoute le numéro de page"""
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#6b7280"))
            page_num = canvas.getPageNumber()
            text = f"Page {page_num}"
            canvas.drawRightString(7.5 * inch, 0.5 * inch, text)
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

        # Récupération et envoi du contenu PDF
        pdf_content = buffer.getvalue()
        buffer.close()
        response.write(pdf_content)
        return response
