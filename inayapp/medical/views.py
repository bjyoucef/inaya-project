import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from accueil.models import ConfigDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from finance.models import Convention, TarifActe, TarifActeConvention
from medecin.models import Medecin
from medical.models import Acte, Prestation, PrestationActe
from patients.models import Patient
from utils.utils import services_autorises


class GetTarifView(View):
    def get(self, request):
        acte_id = request.GET.get("acte_id")
        convention_id = request.GET.get("convention_id")

        try:
            # On récupère l’acte
            acte = Acte.objects.get(pk=acte_id)

            # Tarif par défaut
            tarif = Decimal("0.00")

            if convention_id:
                convention = Convention.objects.get(pk=convention_id)
                # Tarif spécifique à la convention
                tac = (
                    TarifActeConvention.objects.filter(acte=acte, convention=convention)
                    .order_by("-date_effective")
                    .first()
                )
                if tac:
                    tarif = tac.tarif_acte.montant
            else:
                # Tarif de base
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


class PrestationCreateView(View):
    def get(self, request):
        patients = Patient.objects.all()
        medecins = Medecin.objects.all()

        # 1. Récupérer la liste des services autorisés
        # --- Services autorisés
        services = services_autorises(request.user)
        service_ids = services.values_list("id_service", flat=True)

        actes = Acte.objects.prefetch_related("conventions").filter(
            service__id_service__in=service_ids
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
        return render(
            request,
            "medical/prestations/create.html",
            {
                "patients": patients,
                "medecins": medecins,
                "statut_choices": Prestation.STATUT_CHOICES,
                "actes_json": json.dumps(actes_data),
            },
        )

    def post(self, request):
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        date_prestation = request.POST.get("date_prestation")
        statut = request.POST.get("statut")
        observations = request.POST.get("observations", "")
        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")

        errors = []
        prestation_data = []
        total = Decimal("0.00")

        if not (patient_id and medecin_id and date_prestation and statut):
            errors.append("Tous les champs obligatoires doivent être remplis.")

        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Validation des lignes d’acte
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = Acte.objects.get(pk=acte_pk)
                conv = (
                    Convention.objects.get(pk=convention_ids[idx])
                    if convention_ids[idx]
                    else None
                )
                tarif = Decimal(tarifs[idx] or "0")
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                    }
                )
            except Exception as e:
                errors.append(f"Ligne {idx+1} : {e}")

        if errors:
            return render(
                request,
                "medical/prestations/create.html",
                {
                    "errors": errors,
                    "patients": Patient.objects.all(),
                    "medecins": Medecin.objects.all(),
                    "statut_choices": Prestation.STATUT_CHOICES,
                },
            )

        try:
            prestation = Prestation.objects.create(
                patient_id=patient_id,
                medecin_id=medecin_id,
                date_prestation=date_prestation,
                statut=statut,
                observations=observations,
                prix_total=total,
            )
            for d in prestation_data:
                PrestationActe.objects.create(
                    prestation=prestation,
                    acte=d["acte"],
                    convention=d["convention"],
                    tarif_conventionne=d["tarif"],
                )
            return redirect("medical:prestation_detail", prestation_id=prestation.id)
        except Exception as e:
            errors.append(f"Erreur lors de la création : {e}")
            return render(
                request,
                "medical/prestations/create.html",
                {
                    "errors": errors,
                    "patients": Patient.objects.all(),
                    "medecins": Medecin.objects.all(),
                    "statut_choices": Prestation.STATUT_CHOICES,
                },
            )


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
        service_ids = services.values_list("id_service", flat=True)
        
        # --- Filtrage dynamique
        prestations = (
            Prestation.objects.filter(actes__service__id_service__in=service_ids)
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
            "service": ("actes__service__id_service", int),
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

        # Context pour template
        context = {
            "prestations": prestations,
            "medecins": Medecin.objects.filter(prestations__isnull=False).distinct(),
            "patients": Patient.objects.filter(prestations__isnull=False).distinct(),
            "services": services,
            "now": timezone.now(),
            "start_date": start_date,
            "end_date": end_date,
        }
        return render(request, "medical/prestations/list.html", context)


class PrestationDetailView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        return render(
            request,
            "medical/prestations/detail.html",
            {"prestation": prestation, "actes": prestation.actes_details.all()},
        )


from django.views import View
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from decimal import Decimal

from medical.models import Prestation, PrestationActe, Acte
from patients.models import Patient
from medecin.models import Medecin
from finance.models import TarifActe, TarifActeConvention
from utils.utils import services_autorises


class PrestationUpdateView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        # Préparer les listes pour le formulaire
        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        services = services_autorises(request.user)
        actes_qs = Acte.objects.prefetch_related("conventions").filter(
            service__id_service__in=services.values_list("id_service", flat=True)
        )
        # Construire une structure JSON similaire à la création pour le JS
        actes_data = [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": list(acte.conventions.all().values("id", "nom")),
            }
            for acte in actes_qs
        ]
        # Préparer les lignes existantes
        lignes = []
        for pa in prestation.actes_details.all():
            lignes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else "",
                    "tarif": float(pa.tarif_conventionne),
                }
            )
        return render(
            request,
            "medical/prestations/update.html",
            {
                "prestation": prestation,
                "patients": patients,
                "medecins": medecins,
                "statut_choices": Prestation.STATUT_CHOICES,
                "actes_json": json.dumps(actes_data),
                "lignes": json.dumps(lignes),
            },
        )

    def post(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        services = services_autorises(request.user)
        errors = []
        prestation_data = []
        total = Decimal("0.00")

        # Basic field validation
        required_fields = {
            "patient": "Patient requis",
            "medecin": "Médecin requis",
            "date_prestation": "Date de réalisation requise",
            "statut": "Statut requis",
        }
        for field, msg in required_fields.items():
            if not request.POST.get(field):
                errors.append(msg)

        # Process actes
        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        lignes = []

        for idx in range(len(acte_ids)):
            ligne = {
                "acte_id": acte_ids[idx],
                "convention_id": (
                    convention_ids[idx] if idx < len(convention_ids) else ""
                ),
                "tarif": tarifs[idx] if idx < len(tarifs) else "0",
            }
            lignes.append(ligne)

        # Validate each medical act line
        for idx, ligne in enumerate(lignes):
            line_errors = []
            acte_pk = ligne["acte_id"]
            convention_pk = ligne["convention_id"]
            tarif_str = ligne["tarif"]

            # Acte validation
            acte = None
            if acte_pk:
                try:
                    acte = Acte.objects.get(pk=acte_pk)
                    if not acte.service.id_service in services.values_list(
                        "id_service", flat=True
                    ):
                        line_errors.append("Acte non autorisé")
                except Acte.DoesNotExist:
                    line_errors.append("Acte invalide")
            else:
                line_errors.append("Acte non sélectionné")

            # Convention validation
            convention = None
            if convention_pk:
                try:
                    convention = Convention.objects.get(pk=convention_pk)
                    if acte and convention not in acte.conventions.all():
                        line_errors.append("Convention non liée à l'acte")
                except Convention.DoesNotExist:
                    line_errors.append("Convention invalide")

            # Tarif validation
            try:
                tarif = Decimal(tarif_str)
                if tarif < Decimal("0"):
                    line_errors.append("Tarif négatif")
            except InvalidOperation:
                line_errors.append("Tarif invalide")
                tarif = Decimal("0")

            if line_errors:
                errors.extend([f"Ligne {idx+1}: {e}" for e in line_errors])
            else:
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": convention,
                        "tarif": tarif,
                    }
                )
                total += tarif

        if not acte_ids:
            errors.append("Au moins un acte est requis")

        if errors:
            # Regenerate actes data for form
            actes_qs = Acte.objects.prefetch_related("conventions").filter(
                service__id_service__in=services.values_list("id_service", flat=True)
            )
            actes_data = [
                {
                    "id": acte.id,
                    "code": acte.code,
                    "libelle": acte.libelle,
                    "conventions": list(acte.conventions.all().values("id", "nom")),
                }
                for acte in actes_qs
            ]
            return render(
                request,
                "medical/prestations/update.html",
                {
                    "errors": errors,
                    "prestation": prestation,
                    "patients": Patient.objects.all(),
                    "medecins": Medecin.objects.all(),
                    "statut_choices": Prestation.STATUT_CHOICES,
                    "actes_json": json.dumps(actes_data),
                    "lignes": json.dumps(lignes),
                },
            )

        # Update prestation
        prestation.patient_id = request.POST["patient"]
        prestation.medecin_id = request.POST["medecin"]
        prestation.date_prestation = request.POST["date_prestation"]
        prestation.statut = request.POST["statut"]
        prestation.observations = request.POST.get("observations", "")
        prestation.prix_total = total
        prestation.save()

        # Update actes
        prestation.actes_details.all().delete()
        for data in prestation_data:
            PrestationActe.objects.create(
                prestation=prestation,
                acte=data["acte"],
                convention=data["convention"],
                tarif_conventionne=data["tarif"],
            )

        return redirect("medical:prestation_detail", prestation_id=prestation.id)


class PrestationDeleteView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        return render(
            request,
            "medical/prestations/confirm_delete.html",
            {"prestation": prestation},
        )

    def post(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        prestation.delete()
        return redirect("medical:prestation_list")
