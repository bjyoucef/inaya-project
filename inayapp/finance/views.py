# finance/views.py
import copy
import json
import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from accueil.models import ConfigDate
from audit.decorators import audit_view
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models, transaction
from django.db.models import (Avg, CharField, Count, DecimalField,
                              ExpressionWrapper, F, OuterRef, Prefetch, Q,
                              Subquery, Sum, Value)
from django.db.models.functions import Coalesce, Concat, TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from finance.models import Decharges, Payments
from medecin.models import Medecin
from medical.models import ActeKt, ActeProduit, PrestationActe, PrestationKt
from medical.models.prestation_Kt import (ActeKt, ActeProduit, Convention,
                                          PrestationActe, PrestationKt)
from num2words import num2words
from patients.models import Patient
from pharmacies.models import ConsommationProduit, Produit
from rh.models import Personnel, Planning
from utils.pdf import render_to_pdf
from utils.utils import services_autorises
from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator
from .forms import DechargeForm, PaymentForm
from .models import Decharges, PaiementEspecesKt, Payments, TranchePaiementKt


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def add_decharge_multiple(request):
    """
    Crée plusieurs décharges en une seule fois pour les employés sélectionnés
    """
    if request.method != "POST":
        messages.error(request, "Méthode non autorisée.")
        return redirect(reverse("planning"))

    # Récupérer les IDs des employés en filtrant les valeurs vides
    employee_ids = [eid for eid in request.POST.getlist("employeurs") if eid.strip()]

    start_date_str = request.POST.get("start_date", "").strip()
    end_date_str = request.POST.get("end_date", "").strip()
    date_str = request.POST.get("date", "").strip()

    print(f"Start Date: {start_date_str}, End Date: {end_date_str}, Date: {date_str}")
    print(f"Employee IDs: {employee_ids}")

    # Vérifier qu'il y a au moins un employé sélectionné et une date
    if not employee_ids:
        messages.error(request, "Veuillez sélectionner au moins un employé.")
        return redirect(reverse("planning"))

    if not date_str:
        messages.error(request, "La date de décharge est requise.")
        return redirect(reverse("planning"))

    if not start_date_str or not end_date_str:
        messages.error(request, "Les dates de début et fin sont requises.")
        return redirect(reverse("planning"))

    # Parser les dates
    try:
        date_obj = parse_date(date_str)
        start_date_obj = parse_date(start_date_str)
        end_date_obj = parse_date(end_date_str)

        if not all([date_obj, start_date_obj, end_date_obj]):
            messages.error(request, "Format de date invalide.")
            return redirect(reverse("planning"))

    except Exception as e:
        messages.error(request, f"Erreur lors du parsing des dates: {str(e)}")
        return redirect(reverse("planning"))

    errors = []
    success_count = 0

    try:
        # Récupérer l'instance Personnel liée à l'utilisateur connecté
        try:
            personnel_user = Personnel.objects.get(user=request.user)
        except Personnel.DoesNotExist:
            messages.error(request, "Votre profil Personnel n'est pas configuré.")
            return redirect(reverse("planning"))

        with transaction.atomic():
            for emp_id in employee_ids:
                try:
                    # Valider l'ID employé
                    try:
                        emp_id_int = int(emp_id)
                    except ValueError:
                        if emp_id:  # Seulement si l'ID n'est pas vide
                            errors.append(
                                f"Identifiant invalide pour l'employé : {emp_id}"
                            )
                        continue

                    # Récupération de l'employé
                    try:
                        employee_obj = Personnel.objects.get(pk=emp_id_int)
                        full_name = employee_obj.nom_prenom
                    except Personnel.DoesNotExist:
                        errors.append(f"Employé introuvable avec l'ID : {emp_id_int}")
                        continue

                    # Filtrage des plannings pour l'employé sur la période définie
                    # et qui n'ont pas encore de décharge (decharge est null)
                    plannings = Planning.objects.filter(
                        employee_id=emp_id_int,
                        shift_date__range=(start_date_obj, end_date_obj),
                        decharge__isnull=True,  # Corrected: use decharge instead of id_decharge
                        pointage_created_at__isnull=False,  # Only validated plannings
                    )

                    # Calculer le salaire total avec gestion des valeurs nulles
                    aggregation = plannings.aggregate(
                        total_salary=Sum(
                            F("prix") + F("prix_acte"),
                            output_field=DecimalField(max_digits=10, decimal_places=2),
                        )
                    )
                    total_salary = aggregation["total_salary"] or Decimal("0.00")

                    if total_salary <= 0:
                        errors.append(
                            f"L'employé {full_name} n'a pas de salaire positif pour cette période."
                        )
                        continue

                    # Construction des informations de dossiers pour chaque planning filtré
                    dossiers_list = []
                    for p in plannings.select_related(
                        "service", "employee", "shift", "poste"
                    ):
                        service_name = p.service.name if p.service else "Inconnu"
                        shift_name = p.shift.label if p.shift else "Inconnu"
                        poste_name = p.poste.label if p.poste else "Inconnu"

                        dossier = f"{service_name} - {p.shift_date} - {shift_name} - {poste_name} - Garde: {p.prix}"
                        if p.prix_acte and p.prix_acte != 0:
                            dossier += f" - Actes: {p.prix_acte}"
                        dossiers_list.append(dossier)

                    if not dossiers_list:
                        errors.append(
                            f"Aucun planning validé trouvé pour {full_name} sur cette période."
                        )
                        continue

                    # Création de la décharge
                    decharge = Decharges.objects.create(
                        name=full_name,
                        amount=total_salary,
                        date=date_obj,
                        note="\n".join(dossiers_list),
                        created_at=timezone.now(),
                        id_created_par=request.user,
                        id_employe=emp_id_int,
                    )

                    # Mise à jour des plannings concernés avec l'instance de la décharge
                    plannings_updated = plannings.update(
                        decharge=decharge,  # Use the decharge instance, not the ID
                    )

                    success_count += 1
                    print(
                        f"Décharge créée pour {full_name}: {total_salary} DA, {plannings_updated} plannings mis à jour"
                    )

                except Exception as e:
                    errors.append(f"Erreur pour l'employé {emp_id}: {str(e)}")
                    print(f"Erreur pour employé {emp_id}: {str(e)}")
                    continue

        # Messages de retour
        if success_count > 0:
            messages.success(
                request, f"✅ {success_count} décharge(s) créée(s) avec succès."
            )

        if errors:
            for err in errors[:5]:  # Limiter le nombre d'erreurs affichées
                messages.warning(request, err)
            if len(errors) > 5:
                messages.warning(request, f"... et {len(errors) - 5} autres erreurs.")

        if success_count == 0 and errors:
            messages.error(request, "Aucune décharge n'a pu être créée.")

    except Exception as e:
        print(f"Erreur générale: {str(e)}")
        messages.error(
            request, f"Une erreur est survenue lors de l'ajout des décharges: {str(e)}"
        )

    return redirect(reverse("planning"))


@login_required
def decharge_list(request):
    # Base queryset avec les annotations
    base_queryset = (
        Decharges.objects.annotate(
            total_payments=Coalesce(
                Sum("payments__payment"),
                Value(0, output_field=models.DecimalField()),
                output_field=models.DecimalField(),
            )
        )
        .annotate(
            balance=ExpressionWrapper(
                F("amount") - F("total_payments"),
                output_field=models.DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .filter(balance__gt=0)
        .order_by("-date")
    )

    # Séparer par type
    decharges_medecin = base_queryset.filter(medecin__isnull=False)
    decharges_employe = base_queryset.filter(
        id_employe__isnull=False, medecin__isnull=True
    )
    decharges_autre = base_queryset.filter(
        medecin__isnull=True, id_employe__isnull=True
    )

    context = {
        "decharges_medecin": decharges_medecin,
        "decharges_employe": decharges_employe,
        "decharges_autre": decharges_autre,
        "total_medecin": decharges_medecin.count(),
        "total_employe": decharges_employe.count(),
        "total_autre": decharges_autre.count(),
    }

    return render(request, "decharges/decharges_list.html", context)


@login_required
def decharge_settled(request):
    # Base queryset avec les annotations pour les décharges réglées
    base_queryset = (
        Decharges.objects.annotate(
            total_payments=Coalesce(
                Sum("payments__payment", output_field=models.DecimalField()),
                Value(0, output_field=models.DecimalField()),
            )
        )
        .annotate(
            balance=ExpressionWrapper(
                F("amount") - F("total_payments"),
                output_field=models.DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .filter(balance=0)
        .order_by("-date")
    )

    # Séparer par type
    decharges_medecin = base_queryset.filter(medecin__isnull=False)
    decharges_employe = base_queryset.filter(
        id_employe__isnull=False, medecin__isnull=True
    )
    decharges_autre = base_queryset.filter(
        medecin__isnull=True, id_employe__isnull=True
    )

    # Calculer les totaux pour chaque type
    total_amount_medecin = (
        decharges_medecin.aggregate(total=Sum("amount"))["total"] or 0
    )
    total_amount_employe = (
        decharges_employe.aggregate(total=Sum("amount"))["total"] or 0
    )
    total_amount_autre = decharges_autre.aggregate(total=Sum("amount"))["total"] or 0

    # Calculer les totaux des paiements pour chaque type
    total_payments_medecin = (
        decharges_medecin.aggregate(total=Sum("total_payments"))["total"] or 0
    )
    total_payments_employe = (
        decharges_employe.aggregate(total=Sum("total_payments"))["total"] or 0
    )
    total_payments_autre = (
        decharges_autre.aggregate(total=Sum("total_payments"))["total"] or 0
    )

    context = {
        "decharges_medecin": decharges_medecin,
        "decharges_employe": decharges_employe,
        "decharges_autre": decharges_autre,
        "total_medecin": decharges_medecin.count(),
        "total_employe": decharges_employe.count(),
        "total_autre": decharges_autre.count(),
        "total_amount_medecin": total_amount_medecin,
        "total_amount_employe": total_amount_employe,
        "total_amount_autre": total_amount_autre,
        "total_payments_medecin": total_payments_medecin,
        "total_payments_employe": total_payments_employe,
        "total_payments_autre": total_payments_autre,
        "grand_total": total_amount_medecin + total_amount_employe + total_amount_autre,
    }

    return render(request, "decharges/decharges_settled.html", context)


@login_required
@audit_view
def decharge_detail(request, pk):
    decharge = get_object_or_404(Decharges, pk=pk)
    payments = Payments.objects.filter(id_decharge=decharge)

    # Calcul des totaux
    total_payments = payments.aggregate(total=Sum("payment")).get("total") or 0
    balance = decharge.amount - total_payments

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment_amount = form.cleaned_data["payment"]

            if payment_amount > balance:
                messages.error(request, "Le montant dépasse le solde restant!")
            elif balance <= 0:
                messages.error(request, "Le solde est déjà réglé!")
            else:
                payment = form.save(commit=False)
                payment.id_decharge = decharge
                payment.id_payment_par = Personnel.objects.get(user=request.user)
                payment.time_payment = timezone.now()  # Ajout du timestamp
                payment.save()
                messages.success(request, "Paiement ajouté avec succès")
                return redirect("decharge_detail", pk=pk)
    else:
        form = PaymentForm()

    return render(
        request,
        "decharges/decharges_detail.html",
        {
            "decharge": decharge,
            "payments": payments,
            "form": form,
            "total_payments": total_payments,
            "balance": balance,
        },
    )


@login_required
@audit_view
def decharge_create(request):
    if request.method == "POST":
        form = DechargeForm(request.POST)
        if form.is_valid():
            decharge = form.save(commit=False)
            decharge.id_created_par = request.user
            decharge.save()
            messages.success(request, "Décharge créée avec succès")
            return redirect("decharge_list")
    else:
        form = DechargeForm()
    return render(request, "decharges/decharges_form.html", {"form": form})


@login_required
@audit_view
def decharge_edit(request, pk):
    decharge = get_object_or_404(Decharges, pk=pk)
    if request.method == "POST":
        form = DechargeForm(request.POST, instance=decharge)
        if form.is_valid():
            form.save()
            messages.success(request, "Décharge mise à jour avec succès")
            return redirect("decharge_list")
    else:
        form = DechargeForm(instance=decharge)
    return render(request, "decharges/decharges_form.html", {"form": form})


@login_required
@audit_view
def decharge_delete(request, pk):
    decharge = get_object_or_404(Decharges, pk=pk)
    plannings = Planning.objects.filter(id_decharge=decharge)

    if request.method == "POST":
        with transaction.atomic():
            # On dissocie la décharge de tous les plannings
            plannings.update(id_decharge=None)
            # Puis on supprime la décharge
            decharge.delete()
        messages.success(request, "Décharge supprimée avec succès")
        return redirect("decharge_list")
    return render(
        request,
        "decharges/decharges_confirm_delete.html",
        {"decharge": decharge},
    )


@login_required
@audit_view
def payment_delete(request, pk):
    payment = get_object_or_404(Payments, pk=pk)
    decharge_pk = payment.id_decharge.pk
    if request.method == "POST":
        payment.delete()
        messages.success(request, "Paiement supprimé avec succès")
        return redirect("decharge_detail", pk=decharge_pk)
    return render(
        request,
        "decharges/decharges_confirm_payment_delete.html",
        {"payment": payment},
    )


@login_required
@audit_view
def export_decharge_pdf(request, decharge_id):
    decharge = get_object_or_404(Decharges, pk=decharge_id)

    # Récupération des prestations liées
    prestations = decharge.prestation_actes.select_related(
        "prestation__patient", "acte", "convention"
    ).all()

    # Calcul des totaux (à titre de vérification / passage en contexte)
    total_honoraires = sum(p.honoraire_medecin for p in prestations)
    total_supplementaire = sum(
        p.prestation.prix_supplementaire_medecin for p in prestations
    )
    total_general = total_honoraires + total_supplementaire

    amount_in_words = num2words(decharge.amount, lang="fr").capitalize() + " dinars"

    context = {
        "id": decharge.id_decharge,
        "date": decharge.date.strftime("%d/%m/%Y") if decharge.date else "",
        "name": decharge.name,
        "amount": decharge.amount,
        "amount_in_words": amount_in_words,
        "prestations": prestations,
        "total_honoraires": total_honoraires,
        "total_supplementaire": total_supplementaire,
        "total_general": total_general,
    }

    pdf_response = render_to_pdf("decharges/decharge_pdf.html", context)
    if pdf_response:
        decharge.time_export_decharge_pdf = timezone.now()
        decharge.id_export_par = request.user
        decharge.save()

        filename = f"decharge_{decharge.id_decharge}.pdf"
        pdf_response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return pdf_response

    return HttpResponse("Erreur lors de la génération du PDF", status=500)


# views.py
@login_required
@audit_view
def print_decharge_view(request, decharge_id):
    decharge = get_object_or_404(Decharges, pk=decharge_id)
    amount_in_words = num2words(decharge.amount, lang="fr").capitalize() + " dinars"

    context = {
        "id": decharge.id_decharge,
        "date": decharge.date.strftime("%d/%m/%Y") if decharge.date else "",
        "name": (
            decharge.id_created_par.get_full_name() if decharge.id_created_par else ""
        ),
        "amount": decharge.amount,
        "amount_in_words": amount_in_words,
        "dossiers": decharge.note.split("\n") if decharge.note else [],
    }

    return render(request, "decharges/decharge_pdf.html", context)


@audit_view
@permission_required("finance.view_situation_medecins", raise_exception=True)
def situation_medecins_list(request):
    # 1. Sous-requête pour les honoraires
    honoraire_sq = (
        PrestationActe.objects.filter(prestation__medecin=OuterRef("pk"))
        .exclude(prestation__statut="planifie")
        .values("prestation__medecin")
        .annotate(
            total_honoraires_actes=Sum("honoraire_medecin"),
            total_prix_supplementaire=Sum("prestation__prix_supplementaire_medecin"),
        )
        .annotate(total=F("total_honoraires_actes") + F("total_prix_supplementaire"))
        .values("total")
    )

    # 2. Paiements
    paiement_sq = (
        Payments.objects.filter(id_decharge__medecin=OuterRef("pk"))
        .values("id_decharge__medecin")
        .annotate(total=Sum("payment"))
        .values("total")
    )

    # 3. Décharge totales
    decharge_sq = (
        Decharges.objects.filter(medecin=OuterRef("pk"))
        .values("medecin")
        .annotate(total=Sum("amount"))
        .values("total")
    )

    # 4. Query principal - simplifié sans le prefetch
    medecins = (
        Medecin.objects.annotate(
            total_honoraires=Coalesce(
                Subquery(honoraire_sq),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
            total_paiements=Coalesce(
                Subquery(paiement_sq),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
            total_decharges=Coalesce(
                Subquery(decharge_sq),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
        )
        .annotate(
            reste_avec_decharge=ExpressionWrapper(
                F("total_honoraires") - F("total_paiements"),
                output_field=DecimalField(),
            ),
            reste_sans_decharge=ExpressionWrapper(
                F("total_honoraires") - F("total_decharges"),
                output_field=DecimalField(),
            ),
        )
        .order_by("-total_honoraires")
    )

    # 5. Calcul simple du count des décharges non réglées (optionnel pour le badge)
    for med in medecins:
        # Compter les décharges non réglées pour l'affichage du badge
        decharges_non_reglees = (
            Decharges.objects.filter(medecin=med)
            .annotate(
                total_paie=Coalesce(
                    Sum("payments__payment"), Value(0), output_field=DecimalField()
                ),
                solde=F("amount") - F("total_paie"),
            )
            .filter(solde__gt=0)
            .exclude(prestation_actes__prestation__statut="planifie")
            .distinct()
        )

        med.count_non_regle = decharges_non_reglees.count()

    # 6. Totaux globaux simplifiés
    totals = {
        "global_reste_avec": sum(m.reste_avec_decharge for m in medecins),
        "global_reste_sans": sum(m.reste_sans_decharge for m in medecins),
    }

    return render(
        request, "situation_medecins_list.html", {"medecins": medecins, **totals}
    )


@audit_view
@permission_required("finance.view_situation_medecins", raise_exception=True)
def situation_medecin(request, medecin_id):
    medecin = get_object_or_404(Medecin, pk=medecin_id)
    
    
    # Gestion des filtres
    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")
    base_query = (
        PrestationActe.objects
        .filter(prestation__medecin=medecin)
        .exclude(prestation__statut='planifie')
    )

    prestation_query = PrestationKt.objects.filter(medecin=medecin)

    if date_debut and date_fin:
        base_query = base_query.filter(
            Q(prestation__date_prestation__date__gte=date_debut)
            & Q(prestation__date_prestation__date__lte=date_fin)
        )
        prestation_query = prestation_query.filter(
            Q(date_prestation__date__gte=date_debut)
            & Q(date_prestation__date__lte=date_fin)
        )

    # Statistiques globales (incluant prix supplémentaire médecin)
    honoraires_actes = (
        base_query.aggregate(total=Sum("honoraire_medecin"))["total"] or 0
    )
    prix_supplementaire_total = (
        prestation_query.aggregate(total=Sum("prix_supplementaire_medecin"))["total"]
        or 0
    )

    stats = {
        "total_honoraires_actes": honoraires_actes,
        "total_prix_supplementaire": prix_supplementaire_total,
        "total_honoraires": honoraires_actes + prix_supplementaire_total,
        "total_patients": base_query.values("prestation__patient").distinct().count(),
        "total_actes": base_query.values("acte").count() or 0,
    }

    # Préparation des données pour les graphiques
    # Répartition par convention
    conventions_data = (
        base_query.values("convention__nom")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("-total")
    )

    # Ajouter les prix supplémentaires par convention si nécessaire
    # Pour simplifier, on les ajoute à "Sans convention" ou on crée une catégorie spéciale
    if prix_supplementaire_total > 0:
        conventions_data = list(conventions_data)
        conventions_data.append(
            {
                "convention__nom": "Frais supplémentaires",
                "total": prix_supplementaire_total,
            }
        )

    # Top 10 des actes
    actes_data = (
        base_query.values("acte__libelle")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("-total")[:10]
    )

    # Évolution temporelle (incluant prix supplémentaire)
    evolution_actes = (
        base_query.annotate(date=TruncDate("prestation__date_prestation"))
        .values("date")
        .annotate(total=Sum("honoraire_medecin"))
        .order_by("date")
    )

    evolution_supplementaire = (
        prestation_query.annotate(date=TruncDate("date_prestation"))
        .values("date")
        .annotate(total=Sum("prix_supplementaire_medecin"))
        .order_by("date")
    )

    # Combiner les données d'évolution
    evolution_dict = {}
    for item in evolution_actes:
        date = item["date"]
        evolution_dict[date] = evolution_dict.get(date, 0) + item["total"]

    for item in evolution_supplementaire:
        date = item["date"]
        evolution_dict[date] = evolution_dict.get(date, 0) + item["total"]

    evolution_data = [
        {"date": date, "total": total} for date, total in sorted(evolution_dict.items())
    ]

    # Détail des actes bruts
    actes_details = base_query.values(
        "prestation__patient_id",
        "prestation__date_prestation",
        "acte__libelle",
        "convention__nom",
        "honoraire_medecin",
    )

    # Détail des prestations avec prix supplémentaire
    prestations_supplementaires = prestation_query.filter(
        prix_supplementaire_medecin__gt=0
    ).values(
        "patient_id",
        "date_prestation",
        "prix_supplementaire_medecin",
    )

    # Agrégations par patient (incluant prix supplémentaire)
    patients_actes = base_query.values(
        "prestation__patient_id",
        "prestation__patient__last_name",
        "prestation__patient__first_name",
    ).annotate(
        total_honoraires_actes=Sum("honoraire_medecin"),
        nombre_actes=Count("id"),
    )

    patients_supplementaires = prestation_query.values(
        "patient_id",
        "patient__last_name",
        "patient__first_name",
    ).annotate(
        total_prix_supplementaire=Sum("prix_supplementaire_medecin"),
    )

    # Combiner les données patients
    patients_dict = {}
    for p in patients_actes:
        key = p["prestation__patient_id"]
        patients_dict[key] = {
            "prestation__patient_id": key,
            "prestation__patient__last_name": p["prestation__patient__last_name"],
            "prestation__patient__first_name": p["prestation__patient__first_name"],
            "total_honoraires_actes": p["total_honoraires_actes"],
            "nombre_actes": p["nombre_actes"],
            "total_prix_supplementaire": Decimal("0.00"),
        }

    for p in patients_supplementaires:
        key = p["patient_id"]
        if key in patients_dict:
            patients_dict[key]["total_prix_supplementaire"] = p[
                "total_prix_supplementaire"
            ]
        else:
            patients_dict[key] = {
                "prestation__patient_id": key,
                "prestation__patient__last_name": p["patient__last_name"],
                "prestation__patient__first_name": p["patient__first_name"],
                "total_honoraires_actes": Decimal("0.00"),
                "nombre_actes": 0,
                "total_prix_supplementaire": p["total_prix_supplementaire"],
            }

    # Calculer le total final par patient
    for patient_data in patients_dict.values():
        patient_data["total_honoraires"] = (
            patient_data["total_honoraires_actes"]
            + patient_data["total_prix_supplementaire"]
        )

    patients = sorted(
        patients_dict.values(), key=lambda x: x["total_honoraires"], reverse=True
    )

    # Conversion sécurisée des données
    def safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    context = {
        "medecin": medecin,
        "patients": patients,
        "actes_details": actes_details,
        "prestations_supplementaires": prestations_supplementaires,
        "conventions_data": list(conventions_data),
        "actes_data": list(actes_data),
        "evolution_data": evolution_data,
        "stats": stats,
        "convention_labels": [
            c["convention__nom"] or "Non renseigné" for c in conventions_data
        ],
        "convention_values": [safe_float(c.get("total")) for c in conventions_data],
        "acte_labels": [a["acte__libelle"] or "ActeKt inconnu" for a in actes_data],
        "acte_values": [safe_float(a.get("total")) for a in actes_data],
        "evolution_dates": [
            e["date"].isoformat() for e in evolution_data if e.get("date")
        ],
        "medecin": medecin,
        "patients": patients,
        "actes_details": actes_details,
        "conventions_data": list(conventions_data),
        "actes_data": list(actes_data),
        "evolution_data": list(evolution_data),
        "stats": stats,
        # Conversion sécurisée avec gestion des None
        "convention_labels": [
            c["convention__nom"] or "Non renseigné" for c in conventions_data
        ],
        "evolution_totals": [safe_float(e.get("total")) for e in evolution_data],
        "date_debut": date_debut,
        "date_fin": date_fin,
    }

    return render(request, "situation_medecins_kt.html", context)


@audit_view
@permission_required("finance.create_decharge_multiple", raise_exception=True)
def create_decharge_medecin(request, medecin_id):
    medecin = get_object_or_404(Medecin, pk=medecin_id)

    prestations_non_dechargees = (
        PrestationActe.objects.filter(prestation__medecin=medecin)
        .exclude(prestation__statut="planifie",decharges__isnull=False)
        .select_related("prestation", "acte", "convention", "prestation__patient")
    )

    if request.method == "POST":
        # Création de la décharge
        decharge = Decharges.objects.create(
            name=request.POST.get("nom_decharge"),
            amount=0,
            date=request.POST.get("date_decharge"),
            medecin=medecin,
            id_created_par=request.user,
        )

        # Ajout des prestations et construction de la note
        prestation_ids = request.POST.getlist("prestation_acte_ids")
        prestations = PrestationActe.objects.filter(
            id__in=prestation_ids
        ).select_related("prestation")
        decharge.prestation_actes.set(prestations)

        # Génération automatique de la note
        note_content = [
            f"Décharge médicale - Dr. {medecin.nom_complet}\n",
            f"Date de création: {decharge.date}\n\n",
            "Prestations incluses:\n",
        ]

        total_honoraires = 0
        total_supplementaire = 0

        for prestation in prestations:
            details = [
                f"Date: {prestation.prestation.date_prestation.date()}",
                f"ActeKt: {prestation.acte.libelle} ({prestation.acte.code})",
                f"Patient: {prestation.prestation.patient.nom_complet}",
                f"Convention: {prestation.convention.nom if prestation.convention else 'Non conventionné'}",
                f"Honoraire: {prestation.honoraire_medecin} DA\n",
            ]

            # Ajouter le prix supplémentaire médecin s'il existe
            if prestation.prestation.prix_supplementaire_medecin > 0:
                details.append(
                    f"Supplément médecin: {prestation.prestation.prix_supplementaire_medecin} DA"
                )
                total_supplementaire += (
                    prestation.prestation.prix_supplementaire_medecin
                )

            note_content.append(" | ".join(details))
            total_honoraires += prestation.honoraire_medecin

        # Calcul et ajout du total
        total_general = total_honoraires + total_supplementaire

        note_content.append(f"\nRécapitulatif:")
        note_content.append(f"Total honoraires: {total_honoraires} DA")
        if total_supplementaire > 0:
            note_content.append(f"Total suppléments médecin: {total_supplementaire} DA")
        note_content.append(f"Total général: {total_general} DA")

        decharge.note = "\n".join(note_content)
        decharge.amount = total_general
        decharge.save()

        return redirect("decharge_list")

    context = {
        "medecin": medecin,
        "prestations": prestations_non_dechargees,
    }
    return render(request, "decharges/create_decharge_medecin.html", context)


@audit_view
@login_required
@permission_required("medical.manage_conventions", raise_exception=True)
def gestion_convention_accorde_dossier(request):
    """Page de gestion des conventions - exclut urgence"""
    

    # Afficher seulement les actes qui nécessitent une action :
    # - Convention non accordée (None ou False) OU
    # - Dossier incomplet (False)
    # Exclure urgence
    prestation_actes = (
        PrestationActe.objects.filter(convention__isnull=False)
        .exclude(convention__nom__iexact="urgence")  # Exclure urgence
        .filter(
            Q(convention_accordee__in=[None, False])  # En attente ou refusé
            | Q(dossier_convention_complet=False)  # Dossier incomplet
        )
        .select_related(
            "prestation__patient", "prestation__medecin", "acte", "convention"
        )
    )

    # Filtres
    search = request.GET.get("search", "")
    if search:
        prestation_actes = prestation_actes.filter(
            Q(prestation__patient__first_name__icontains=search)
            | Q(prestation__patient__last_name__icontains=search)
            | Q(acte__code__icontains=search)
            | Q(acte__libelle__icontains=search)
        )

    current_status = request.GET.get("status", "")
    if current_status == "en_attente":
        prestation_actes = prestation_actes.filter(convention_accordee__isnull=True)
    elif current_status == "accorde":
        prestation_actes = prestation_actes.filter(convention_accordee=True)
    elif current_status == "non_accorde":
        prestation_actes = prestation_actes.filter(convention_accordee=False)

    dossier_filter = request.GET.get("dossier", "")
    if dossier_filter == "complet":
        prestation_actes = prestation_actes.filter(dossier_convention_complet=True)
    elif dossier_filter == "incomplet":
        prestation_actes = prestation_actes.filter(dossier_convention_complet=False)

    current_medecin = request.GET.get("medecin", "")
    if current_medecin:
        prestation_actes = prestation_actes.filter(prestation__medecin_id=current_medecin)

    date_debut = request.GET.get("date_debut")
    if date_debut:
        prestation_actes = prestation_actes.filter(prestation__date_prestation__gte=date_debut)

    # Pagination

    paginator = Paginator(prestation_actes, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Médecins pour le filtre

    medecins = Medecin.objects.all().order_by("last_name", "first_name")

    context = {
        "prestation_actes": page_obj,
        "page_obj": page_obj,
        "search": search,
        "current_status": current_status,
        "current_medecin": current_medecin,
        "medecins": medecins,
    }

    return render(request, "facturation_KT/accord_dossier.html", context)


@audit_view
@login_required
@permission_required('medical.manage_conventions', raise_exception=True)
def update_convention_status(request, pk):
    if not request.user.has_perm("medical.change_prestationacte"):
        return JsonResponse({"error": "Permission refusée"}, status=403)

    prestation_acte = get_object_or_404(PrestationActe, pk=pk)
    action = request.GET.get("action")

    response_data = {
        "status": "success",
        "new_status": prestation_acte.convention_accordee,  # Valeur actuelle par défaut
        "dossier_status": prestation_acte.dossier_convention_complet,  # Valeur actuelle par défaut
        "message": "",
        "stats": {},
    }

    try:
        # Traiter uniquement l'action demandée
        if action == "approve":
            prestation_acte.convention_accordee = True
            response_data["new_status"] = True
            response_data["message"] = (
                f"Convention {prestation_acte.convention} approuvée"
            )

        elif action == "dossier_complet":
            prestation_acte.dossier_convention_complet = True
            response_data["dossier_status"] = True
            response_data["message"] = "Dossier de convention marqué comme complet"

        else:
            raise ValueError("Action invalide")

        # Valider et sauvegarder
        prestation_acte.full_clean()
        prestation_acte.save()

        # Stats — appliquer la même exclusion pour que les compteurs reflètent la table affichée
        qs = PrestationActe.objects.filter(convention__isnull=False).exclude(
            convention_accordee=True, dossier_convention_complet=True
        )
        total = qs.count()
        en_attente = qs.filter(convention_accordee__isnull=True).count()
        accorde = qs.filter(convention_accordee=True).count()
        refuse = qs.filter(convention_accordee=False).count()
        dossier_complet = qs.filter(dossier_convention_complet=True).count()
        dossier_incomplet = qs.filter(dossier_convention_complet=False).count()

        response_data["stats"] = {
            "total": qs.count(),
            "en_attente": qs.filter(convention_accordee__isnull=True).count(),
            "accorde": qs.filter(convention_accordee=True).count(),
            "refuse": qs.filter(convention_accordee=False).count(),
            "dossier_complet": qs.filter(dossier_convention_complet=True).count(),
            "dossier_incomplet": qs.filter(dossier_convention_complet=False).count(),
        }

        # Mettre à jour seulement les valeurs qui ont changé
        if action in ["approve", "reject", "reset"]:
            # Seul le statut d'accord a changé, garder le statut dossier actuel
            response_data["dossier_status"] = prestation_acte.dossier_convention_complet
        elif action in ["dossier_complet", "dossier_incomplet"]:
            # Seul le statut dossier a changé, garder le statut d'accord actuel
            response_data["new_status"] = prestation_acte.convention_accordee

    except ValidationError as e:
        response_data = {
            "status": "error",
            "message": f"Erreur de validation : {e.message_dict if hasattr(e, 'message_dict') else str(e)}",
        }
    except Exception as e:
        response_data = {"status": "error", "message": str(e)}

    # Retourner JSON pour les requêtes AJAX, redirection sinon
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(response_data)
    else:
        if response_data["status"] == "success":
            messages.success(request, response_data["message"])
        else:
            messages.error(request, response_data["message"])
        return redirect("gestion_convention_accorde_dossier")


@permission_required("medical.facturer_prestationacte", raise_exception=True)
def actes_a_facturer(request):
    """Page listant les actes prêts à être facturés"""

    # Filtrer les actes qui peuvent être facturés (exclure urgence)
    actes = (
        PrestationActe.objects.filter(
            statut_facturation="A_FACTURER",
            convention__isnull=False,
            convention_accordee=True,
            dossier_convention_complet=True,
        )
        .exclude(convention__nom__iexact="urgence")  # Exclure urgence
        .select_related(
            "prestation__patient", "prestation__medecin", "acte", "convention"
        )
        .order_by("-prestation__date_prestation")
    )

    # Recherche simple "last_name", "first_name"
    search = request.GET.get("search", "")
    if search:
        actes = actes.filter(
            Q(prestation__patient__last_name__icontains=search)
            | Q(prestation__patient__first_name__icontains=search)
            | Q(acte__code__icontains=search)
            | Q(acte__libelle__icontains=search)
        )

    # Filtres
    convention_id = request.GET.get("convention")
    if convention_id:
        actes = actes.filter(convention_id=convention_id)

    medecin_id = request.GET.get("medecin")
    if medecin_id:
        actes = actes.filter(prestation__medecin_id=medecin_id)

    # Pagination
    paginator = Paginator(actes, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Statistiques
    total_actes = actes.count()
    montant_total = actes.aggregate(total=Sum("tarif_conventionne"))[
        "total"
    ] or Decimal("0.00")

    # Données pour les filtres

    conventions = Convention.objects.filter(active=True)
    medecins = Medecin.objects.all().order_by("last_name", "first_name")

    context = {
        "page_obj": page_obj,
        "total_actes": total_actes,
        "montant_total": montant_total,
        "search": search,
        "conventions": conventions,
        "medecins": medecins,
        "selected_convention": convention_id,
        "selected_medecin": medecin_id,
    }

    return render(request, "facturation_KT/actes_a_facturer.html", context)


@permission_required("medical.facturer_prestationacte", raise_exception=True)
def facturer_acte(request, acte_id):
    """Marquer un acte comme facturé"""
    if request.method == "POST":
        acte = get_object_or_404(PrestationActe, id=acte_id)

        try:
            # Vérifier que l'acte peut être facturé
            if not acte.peut_facturer_convention:
                messages.error(
                    request, "Cet acte ne peut pas être facturé en convention."
                )
                return redirect("actes_a_facturer")

            # Facturer l'acte
            result = acte.facturer()
            messages.success(request, f"Acte facturé avec succès. {result}")

        except Exception as e:
            messages.error(request, f"Erreur lors de la facturation: {str(e)}")

    return redirect("actes_a_facturer")


@permission_required("medical.view_facturation_details", raise_exception=True)
def actes_factures(request):
    """Page listant les actes facturés en attente de règlement"""

    # Filtrer les actes facturés (en attente de paiement) - exclure urgence
    actes = (
        PrestationActe.objects.filter(
            statut_facturation="FACTURE"
        )
        .exclude(convention__nom__iexact="urgence")  # Exclure urgence
        .select_related(
            "prestation__patient", "prestation__medecin", "acte", "convention"
        )
        .order_by("-date_facturation")
    )

    # Recherche
    search = request.GET.get("search", "")
    if search:
        actes = actes.filter(
            Q(prestation__patient__last_name__icontains=search)
            | Q(prestation__patient__first_name__icontains=search)
            | Q(acte__code__icontains=search)
            | Q(acte__libelle__icontains=search)
        )

    # Filtres
    convention_id = request.GET.get("convention")
    if convention_id:
        actes = actes.filter(convention_id=convention_id)

    medecin_id = request.GET.get("medecin")
    if medecin_id:
        actes = actes.filter(prestation__medecin_id=medecin_id)

    # Filtre par retard de paiement
    en_retard = request.GET.get("en_retard")
    if en_retard == "1":

        date_limite = timezone.now().date() - timezone.timedelta(days=30)
        actes = actes.filter(date_facturation__lt=date_limite)

    # Pagination
    paginator = Paginator(actes, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Statistiques
    total_actes = actes.count()
    montant_total = actes.aggregate(total=Sum("tarif_conventionne"))[
        "total"
    ] or Decimal("0.00")

    # Actes en retard de paiement

    date_limite = timezone.now().date() - timezone.timedelta(days=30)
    actes_en_retard = PrestationActe.objects.filter(
        statut_facturation="FACTURE", date_facturation__lt=date_limite
    ).count()

    # Données pour les filtres

    conventions = Convention.objects.filter(active=True)
    medecins = Medecin.objects.all().order_by("last_name", "first_name")

    context = {
        "page_obj": page_obj,
        "total_actes": total_actes,
        "montant_total": montant_total,
        "actes_en_retard": actes_en_retard,
        "search": search,
        "conventions": conventions,
        "medecins": medecins,
        "selected_convention": convention_id,
        "selected_medecin": medecin_id,
        "en_retard_filter": en_retard,
    }

    return render(request, "facturation_KT/actes_factures.html", context)


@permission_required("medical.payer_prestationacte", raise_exception=True)
def marquer_paye_acte(request, acte_id):
    """Marquer un acte comme payé (paiement complet)"""
    if request.method == "POST":
        acte = get_object_or_404(PrestationActe, id=acte_id)

        try:
            # Marquer comme payé
            result = acte.marquer_paye()
            messages.success(request, f"Acte marqué comme payé avec succès. {result}")

        except Exception as e:
            messages.error(request, f"Erreur lors du marquage de paiement: {str(e)}")

    return redirect("actes_factures")


@permission_required("medical.rejeter_prestationacte", raise_exception=True)
def rejeter_acte(request, acte_id):
    """Marquer un acte comme rejeté"""
    if request.method == "POST":
        acte = get_object_or_404(PrestationActe, id=acte_id)

        motif = request.POST.get("motif", "").strip()
        if not motif:
            messages.error(request, "Le motif de rejet est requis.")
            return redirect("actes_factures")

        try:
            result = acte.marquer_rejete(motif)
            messages.success(request, f"Acte marqué comme rejeté. {result}")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")

    return redirect("actes_factures")


@permission_required("medical.view_facturation_details", raise_exception=True)
def actes_payes(request):
    """Page listant les actes payés"""

    # Filtrer les actes payés - exclure urgence
    actes = (
        PrestationActe.objects.filter(
            statut_facturation="PAYE"
        )
        .exclude(convention__nom__iexact="urgence")  # Exclure urgence
        .select_related(
            "prestation__patient", "prestation__medecin", "acte", "convention"
        )
        .order_by("-date_paiement")
    )

    # Recherche
    search = request.GET.get("search", "")
    if search:
        actes = actes.filter(
            Q(prestation__patient__last_name__icontains=search)
            | Q(prestation__patient__first_name__icontains=search)
            | Q(acte__code__icontains=search)
            | Q(acte__libelle__icontains=search)
        )

    # Filtres
    convention_id = request.GET.get("convention")
    if convention_id:
        actes = actes.filter(convention_id=convention_id)

    medecin_id = request.GET.get("medecin")
    if medecin_id:
        actes = actes.filter(prestation__medecin_id=medecin_id)

    # Filtre par période
    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")
    if date_debut:
        actes = actes.filter(date_paiement__gte=date_debut)
    if date_fin:
        actes = actes.filter(date_paiement__lte=date_fin)

    # Pagination
    paginator = Paginator(actes, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Statistiques
    total_actes = actes.count()
    montant_total = actes.aggregate(total=Sum("tarif_conventionne"))[
        "total"
    ] or Decimal("0.00")

    # Données pour les filtres

    conventions = Convention.objects.filter(active=True)
    medecins = Medecin.objects.all().order_by("last_name", "first_name")

    context = {
        "page_obj": page_obj,
        "total_actes": total_actes,
        "montant_total": montant_total,
        "search": search,
        "conventions": conventions,
        "medecins": medecins,
        "selected_convention": convention_id,
        "selected_medecin": medecin_id,
        "date_debut": date_debut,
        "date_fin": date_fin,
    }

    return render(request, "facturation_KT/actes_payes.html", context)


@permission_required("medical.view_facturation_details", raise_exception=True)
def actes_rejetes(request):
    """Page listant les actes rejetés"""

    # Filtrer les actes rejetés - exclure urgence
    actes = (
        PrestationActe.objects.filter(
            statut_facturation="REJETE"
        )
        .exclude(convention__nom__iexact="urgence")  # Exclure urgence
        .select_related(
            "prestation__patient", "prestation__medecin", "acte", "convention"
        )
        .order_by("-date_rejet")
    )

    # Recherche
    search = request.GET.get("search", "")
    if search:
        actes = actes.filter(
            Q(prestation__patient__last_name__icontains=search)
            | Q(prestation__patient__first_name__icontains=search)
            | Q(acte__code__icontains=search)
            | Q(acte__libelle__icontains=search)
            | Q(motif_rejet__icontains=search)
        )

    # Filtres
    convention_id = request.GET.get("convention")
    if convention_id:
        actes = actes.filter(convention_id=convention_id)

    medecin_id = request.GET.get("medecin")
    if medecin_id:
        actes = actes.filter(prestation__medecin_id=medecin_id)

    # Pagination
    paginator = Paginator(actes, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Statistiques
    total_actes = actes.count()
    montant_total = actes.aggregate(total=Sum("tarif_conventionne"))[
        "total"
    ] or Decimal("0.00")

    # Données pour les filtres

    conventions = Convention.objects.filter(active=True)
    medecins = Medecin.objects.all().order_by("last_name", "first_name")

    context = {
        "page_obj": page_obj,
        "total_actes": total_actes,
        "montant_total": montant_total,
        "search": search,
        "conventions": conventions,
        "medecins": medecins,
        "selected_convention": convention_id,
        "selected_medecin": medecin_id,
    }

    return render(request, "facturation_KT/actes_rejetes.html", context)


@permission_required("medical.view_facturation_details", raise_exception=True)
def tableau_bord_facturation(request):
    """Tableau de bord avec statistiques générales"""

    # Statistiques générales - exclure urgence
    base_qs = PrestationActe.objects.exclude(convention__nom__iexact="urgence")

    stats = {
        'a_facturer': base_qs.filter(statut_facturation="A_FACTURER").count(),
        'factures': base_qs.filter(statut_facturation="FACTURE").count(),
        'payes': base_qs.filter(statut_facturation="PAYE").count(),
        'rejetes': base_qs.filter(statut_facturation="REJETE").count(),
    }

    # Montants - exclure urgence
    montants = {
        'a_facturer': base_qs.filter(
            statut_facturation="A_FACTURER"
        ).aggregate(total=Sum("tarif_conventionne"))["total"]
        or Decimal("0.00"),
        'factures': base_qs.filter(
            statut_facturation="FACTURE"
        ).aggregate(total=Sum("tarif_conventionne"))["total"]
        or Decimal("0.00"),
        'payes': base_qs.filter(
            statut_facturation="PAYE"
        ).aggregate(total=Sum("tarif_conventionne"))["total"] or Decimal("0.00"),
        'rejetes': base_qs.filter(
            statut_facturation="REJETE"
        ).aggregate(total=Sum("tarif_conventionne"))["total"] or Decimal("0.00"),
    }

    # Actes en retard - exclure urgence

    date_limite = timezone.now().date() - timezone.timedelta(days=30)
    actes_en_retard = base_qs.filter(
        statut_facturation="FACTURE", date_facturation__lt=date_limite
    ).count()

    # Répartition par convention - exclure urgence
    conventions_stats = base_qs.filter(
        statut_facturation__in=["FACTURE", "PAYE"]
    ).values(
        "convention__nom"
    ).annotate(
        count=Count("id"),
        montant=Sum("tarif_conventionne")
    ).order_by("-montant")[:10]

    context = {
        "stats": stats,
        "montants": montants,
        "actes_en_retard": actes_en_retard,
        "conventions_stats": conventions_stats,
    }

    return render(request, "facturation_KT/tableau_bord.html", context)


@method_decorator(
    permission_required("medical.manage_paiements_especes", raise_exception=True),
    name="dispatch",
)
class PrestationsEspecesEnAttenteView(View):
    """Vue pour afficher les prestations avec paiements espèces en attente"""
    
    def get(self, request):
        
        # Vérifier si c'est une requête AJAX pour le badge
        if request.GET.get("ajax") == "1":
            return self._get_ajax_count(request)

        # Configuration des dates
        config, _ = ConfigDate.objects.get_or_create(
            user=request.user,
            page="prestations_especes_attente",
            defaults={
                "start_date": date.today() - timedelta(days=30),
                "end_date": date.today(),
            },
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

        # CORRECTION: Récupérer TOUTES les prestations réalisées puis filtrer celles qui ont des éléments espèces
        prestations_candidates = (
            PrestationKt.objects.filter(
                statut__in=["REALISE"],
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
                ),
                "paiement_especes__tranches",
            )
            .order_by("-date_prestation")
        )

        # Application des filtres de date
        if start_date:
            prestations_candidates = prestations_candidates.filter(
                date_prestation__gte=start_date
            )
        if end_date:
            prestations_candidates = prestations_candidates.filter(
                date_prestation__lte=end_date
            )

        # Filtres supplémentaires
        filtres = {
            "medecin": ("medecin_id", int),
            "patient": ("patient_id", int),
        }

        for param, (field, caster) in filtres.items():
            val = request.GET.get(param)
            if not val:
                continue

            try:
                val = caster(val) if caster else val
                prestations_candidates = prestations_candidates.filter(**{field: val})
            except (ValueError, TypeError):
                continue

        # CORRECTION: Filtrer pour ne garder que les prestations avec éléments espèces non payés
        prestations_with_totals = []
        total_general_attente = Decimal("0.00")

        for prestation in prestations_candidates:
            # Vérifier s'il y a des éléments à payer en espèces
            has_elements_especes = self._has_especes_elements(prestation)

            if not has_elements_especes:
                continue

            # Vérifier le statut de paiement espèces
            try:
                paiement_especes = prestation.paiement_especes
                # Si paiement complet, ignorer cette prestation
                if paiement_especes.statut == "COMPLET":
                    continue
            except PaiementEspecesKt.DoesNotExist:
                # Pas de paiement espèces = en attente
                pass

            # Calculer le total espèces pour cette prestation
            total_especes = self._calculate_total_especes(prestation)
            paiement_info = self._get_paiement_info(prestation)

            # Récupérer les actes espèces pour affichage
            actes_especes = prestation.actes_details.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            )

            prestations_with_totals.append(
                {
                    "prestation": prestation,
                    "total_especes": total_especes,
                    "actes_especes": actes_especes,
                    "paiement_info": paiement_info,
                    "has_frais_supplementaires": prestation.prix_supplementaire > 0,
                    "has_consommations_supplementaires": self._has_consommations_supplementaires(
                        prestation
                    ),
                }
            )

            # Ne compter dans le total que ce qui reste à payer
            total_general_attente += paiement_info["montant_restant"]

        # Pagination
        items_per_page = min(max(int(request.GET.get("per_page", 25)), 10), 100)
        paginator = Paginator(prestations_with_totals, items_per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "paginator": paginator,
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "items_per_page": items_per_page,
            "total_count": paginator.count,
            "total_general_attente": total_general_attente,
            "medecins": Medecin.objects.filter(prestations__isnull=False).distinct(),
            "patients": Patient.objects.filter(prestations__isnull=False).distinct(),
            "start_date": start_date,
            "end_date": end_date,
            "page_title": "Prestations Espèces - En Attente de Paiement",
        }

        return render(request, "facturation_KT/especes_en_attente.html", context)

    def _has_especes_elements(self, prestation):
        """Vérifie si une prestation a des éléments à payer en espèces"""
        

        # 1. Actes sans convention ou urgence
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )
        if actes_especes.exists():
            return True

        # 2. Frais supplémentaires
        if prestation.prix_supplementaire > 0:
            return True

        # 3. Consommations supplémentaires (sur n'importe quel acte)
        if self._has_consommations_supplementaires(prestation):
            return True

        return False

    def _has_consommations_supplementaires(self, prestation):
        """Vérifie s'il y a des consommations supplémentaires"""
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    return True
        return False

    def _calculate_total_especes(self, prestation):
        """Calcule le total espèces pour une prestation"""
        total_especes = Decimal("0.00")
        

        # 1. Actes espèces (sans convention ou urgence)
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )

        for pa in actes_especes:
            total_especes += pa.tarif_conventionne

        # 2. Consommations supplémentaires (sur TOUS les actes, même conventionnés)
        for pa in prestation.actes_details.all():
            for conso in pa.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supp = conso.quantite_reelle - conso.quantite_defaut
                    total_especes += quantite_supp * conso.prix_unitaire

        # 3. Frais supplémentaires
        total_especes += prestation.prix_supplementaire

        return total_especes

    def _get_paiement_info(self, prestation):
        """Récupère les informations de paiement pour une prestation"""
        total_especes = self._calculate_total_especes(prestation)

        try:
            paiement_especes = prestation.paiement_especes
            montant_paye = paiement_especes.montant_paye
            montant_restant = paiement_especes.montant_restant
            statut = paiement_especes.statut
        except PaiementEspecesKt.DoesNotExist:
            montant_paye = Decimal("0.00")
            montant_restant = total_especes
            statut = "EN_COURS"

        return {
            "total_especes": total_especes,
            "montant_paye": montant_paye,
            "montant_restant": montant_restant,
            "statut": statut,
            "pourcentage_paye": (
                (montant_paye / total_especes * 100) if total_especes > 0 else 0
            ),
        }

    def _get_ajax_count(self, request):
        """Retourne le nombre de prestations en attente en JSON pour le badge"""
        # Compter les prestations en attente (derniers 30 jours)
        date_limite = date.today() - timedelta(days=30)

        prestations_candidates = PrestationKt.objects.filter(
            statut__in=["REALISE"],
            date_prestation__gte=date_limite,
        ).prefetch_related("actes_details__consommations", "paiement_especes")

        count = 0
        for prestation in prestations_candidates:
            # Vérifier s'il y a des éléments espèces
            if not self._has_especes_elements(prestation):
                continue

            # Vérifier le statut de paiement
            try:
                paiement_especes = prestation.paiement_especes
                if paiement_especes.statut == "COMPLET":
                    continue
            except PaiementEspecesKt.DoesNotExist:
                pass

            count += 1

        return JsonResponse({"count": count, "success": True})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    permission_required("medical.manage_paiements_especes", raise_exception=True),
    name="dispatch",
)
class GestionPaiementEspecesView(View):
    """Vue pour gérer les paiements espèces via Ajax"""

    def get(self, request, prestation_id):
        """Retourne les détails de paiement pour une prestation"""
        try:
            

            prestation = get_object_or_404(PrestationKt, id=prestation_id)

            # CORRECTION: Vérifier que la prestation a des éléments espèces (pas seulement des actes)
            if not self._has_especes_elements(prestation):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Cette prestation ne contient aucun élément payable en espèces",
                    }
                )

            # Calculer le total espèces (actes + consommations + frais)
            total_especes = self._calculate_total_especes(prestation)

            # Récupérer ou créer le paiement espèces
            paiement_especes, created = PaiementEspecesKt.objects.get_or_create(
                prestation=prestation,
                defaults={"montant_total_du": total_especes, "cree_par": request.user},
            )

            # Récupérer les tranches de paiement
            tranches = paiement_especes.tranches.all().order_by("-date_paiement")

            # Récupérer les actes espèces pour affichage
            actes_especes = prestation.actes_details.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            )

            data = {
                "success": True,
                "prestation": {
                    "id": prestation.id,
                    "patient": prestation.patient.nom_complet,
                    "date": prestation.date_prestation.strftime("%d/%m/%Y %H:%M"),
                    "medecin": f"Dr. {prestation.medecin.nom_complet}",
                },
                "paiement": {
                    "id": paiement_especes.id,
                    "montant_total_du": float(paiement_especes.montant_total_du),
                    "montant_paye": float(paiement_especes.montant_paye),
                    "montant_restant": float(paiement_especes.montant_restant),
                    "statut": paiement_especes.statut,
                    "pourcentage_paye": (
                        float(
                            paiement_especes.montant_paye
                            / paiement_especes.montant_total_du
                            * 100
                        )
                        if paiement_especes.montant_total_du > 0
                        else 0
                    ),
                },
                "tranches": [
                    {
                        "id": tranche.id,
                        "montant": float(tranche.montant),
                        "date_paiement": tranche.date_paiement.strftime(
                            "%d/%m/%Y %H:%M"
                        ),
                        "encaisse_par": tranche.encaisse_par.get_full_name()
                        or tranche.encaisse_par.username,
                        "notes": tranche.notes,
                    }
                    for tranche in tranches
                ],
                # CORRECTION: Inclure tous les éléments espèces, pas seulement les actes
                "elements_especes": self._get_elements_especes_detail(
                    prestation, actes_especes
                ),
            }

            return JsonResponse(data)

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    def post(self, request, prestation_id):
        """Enregistre un nouveau paiement"""
        try:
            with transaction.atomic():
                prestation = get_object_or_404(PrestationKt, id=prestation_id)

                # Récupérer les données du paiement
                data = json.loads(request.body)
                montant = Decimal(str(data.get("montant", 0)))
                notes = data.get("notes", "")

                if montant <= 0:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Le montant doit être supérieur à 0",
                        }
                    )

                # CORRECTION: Vérifier qu'il y a des éléments espèces (pas seulement des actes)
                if not self._has_especes_elements(prestation):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Cette prestation ne contient aucun élément payable en espèces",
                        }
                    )

                # Calculer le total espèces
                total_especes = self._calculate_total_especes(prestation)

                paiement_especes, created = PaiementEspecesKt.objects.get_or_create(
                    prestation=prestation,
                    defaults={
                        "montant_total_du": total_especes,
                        "cree_par": request.user,
                    },
                )

                # Vérifier si le montant ne dépasse pas ce qui reste à payer
                if not paiement_especes.peut_recevoir_paiement(montant):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"Le montant dépasse ce qui reste à payer ({paiement_especes.montant_restant} DA)",
                        }
                    )

                # Créer la tranche de paiement
                tranche = TranchePaiementKt.objects.create(
                    paiement_especes=paiement_especes,
                    montant=montant,
                    encaisse_par=request.user,
                    notes=notes,
                )

                # Actualiser l'objet paiement_especes depuis la DB
                paiement_especes.refresh_from_db()

                # Actualiser l'objet prestation depuis la DB
                prestation.refresh_from_db()

                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Paiement de {montant} DA enregistré avec succès",
                        "tranche_id": tranche.id,
                        "nouveau_montant_paye": float(paiement_especes.montant_paye),
                        "nouveau_montant_restant": float(
                            paiement_especes.montant_restant
                        ),
                        "statut": paiement_especes.statut,
                        "prestation_payee": paiement_especes.est_complet,
                        "statut_prestation": prestation.statut,
                    }
                )

        except ValueError:
            return JsonResponse({"success": False, "message": "Montant invalide"})
        except ValidationError as e:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Erreur de validation: {'; '.join(e.messages)}",
                }
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Erreur lors de l'enregistrement: {str(e)}",
                }
            )

    def _has_especes_elements(self, prestation):
        """Vérifie si une prestation a des éléments à payer en espèces"""
          # Import local
        
        # 1. Actes sans convention ou urgence
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )
        if actes_especes.exists():
            return True

        # 2. Frais supplémentaires
        if prestation.prix_supplementaire > 0:
            return True

        # 3. Consommations supplémentaires (sur n'importe quel acte)
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    return True

        return False

    def _calculate_total_especes(self, prestation):
        """Calcule le total espèces pour une prestation"""
          # Import local
        
        total_especes = Decimal("0.00")

        # 1. Actes espèces (sans convention ou urgence)
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )

        for pa in actes_especes:
            total_especes += pa.tarif_conventionne

        # 2. Consommations supplémentaires (sur TOUS les actes, même conventionnés)
        for pa in prestation.actes_details.all():
            for conso in pa.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supp = conso.quantite_reelle - conso.quantite_defaut
                    total_especes += quantite_supp * conso.prix_unitaire

        # 3. Frais supplémentaires
        total_especes += prestation.prix_supplementaire

        return total_especes

    def _get_elements_especes_detail(self, prestation, actes_especes):
        """Retourne le détail de tous les éléments espèces"""
        elements = []

        # 1. Actes espèces
        for acte in actes_especes:
            elements.append(
                {
                    "type": "acte",
                    "code": acte.acte.code,
                    "libelle": acte.acte.libelle,
                    "tarif": float(acte.tarif_conventionne),
                    "convention": (
                        acte.convention.nom if acte.convention else "Sans convention"
                    ),
                }
            )

        # 2. Consommations supplémentaires (sur tous les actes)
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supp = conso.quantite_reelle - conso.quantite_defaut
                    montant_conso = quantite_supp * conso.prix_unitaire
                    elements.append(
                        {
                            "type": "consommation",
                            "code": f"+ {conso.produit.code_produit}",
                            "libelle": f"{conso.produit.nom} (qté supp: {quantite_supp})",
                            "tarif": float(montant_conso),
                            "convention": "Consommation supplémentaire",
                        }
                    )

        # 3. Frais supplémentaires
        if prestation.prix_supplementaire > 0:
            elements.append(
                {
                    "type": "frais",
                    "code": "SUPP",
                    "libelle": "Frais supplémentaires",
                    "tarif": float(prestation.prix_supplementaire),
                    "convention": "Frais supplémentaires",
                }
            )

        return elements


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    permission_required("medical.manage_paiements_especes", raise_exception=True),
    name="dispatch",
)
class SupprimerTranchePaiementView(View):
    """Vue pour supprimer une tranche de paiement"""

    def delete(self, request, tranche_id):
        try:
            with transaction.atomic():
                tranche = get_object_or_404(TranchePaiementKt, id=tranche_id)
                paiement_especes = tranche.paiement_especes
                prestation = paiement_especes.prestation

                # Supprimer la tranche (cela va déclencher la mise à jour via delete())
                tranche.delete()

                # CORRECTION: Actualiser les objets depuis la DB
                paiement_especes.refresh_from_db()
                prestation.refresh_from_db()

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Tranche de paiement supprimée",
                        "nouveau_montant_paye": float(paiement_especes.montant_paye),
                        "nouveau_montant_restant": float(
                            paiement_especes.montant_restant
                        ),
                        "statut": paiement_especes.statut,
                        "statut_prestation": prestation.statut,  # AJOUT: Retourner le statut de la prestation
                    }
                )

        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Erreur lors de la suppression: {str(e)}",
                }
            )


@method_decorator(
    permission_required("medical.view_paiements_especes", raise_exception=True),
    name="dispatch",
)
class PrestationsEspecesPayeesView(View):
    """Vue pour afficher les prestations avec paiements espèces complètement réglés"""

    def get(self, request):
        # Configuration des dates

        config, _ = ConfigDate.objects.get_or_create(
            user=request.user,
            page="prestations_especes_payees",
            defaults={
                "start_date": date.today() - timedelta(days=30),
                "end_date": date.today(),
            },
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

        # CORRECTION: Récupérer les prestations avec paiements espèces complets
        prestations = (
            PrestationKt.objects.filter(
                paiement_especes__statut="COMPLET",
            )
            .select_related("patient", "medecin")
            .prefetch_related(
                "paiement_especes__tranches",
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
                ),
            )
            .distinct()
            .order_by("-date_prestation")
        )

        # Application des filtres de date
        if start_date:
            prestations = prestations.filter(date_prestation__gte=start_date)
        if end_date:
            prestations = prestations.filter(date_prestation__lte=end_date)

        # Filtres supplémentaires
        filtres = {
            "medecin": ("medecin_id", int),
            "patient": ("patient_id", int),
        }

        for param, (field, caster) in filtres.items():
            val = request.GET.get(param)
            if not val:
                continue

            try:
                val = caster(val) if caster else val
                prestations = prestations.filter(**{field: val})
            except (ValueError, TypeError):
                continue

        # CORRECTION: Filtrer pour ne garder que les prestations qui avaient vraiment des éléments espèces
        prestations_with_totals = []
        total_general_paye = Decimal("0.00")

        for prestation in prestations:
            # Vérifier que cette prestation avait des éléments espèces
            if not self._has_especes_elements(prestation):
                continue

            paiement_info = {
                "total_especes": prestation.paiement_especes.montant_total_du,
                "montant_paye": prestation.paiement_especes.montant_paye,
                "date_completion": prestation.paiement_especes.date_completion,
                "tranches_count": prestation.paiement_especes.tranches.count(),
            }

            # Récupérer les actes espèces pour affichage (même logique que dans "en attente")
            actes_especes = prestation.actes_details.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            )

            prestations_with_totals.append(
                {
                    "prestation": prestation,
                    "total_especes": paiement_info["total_especes"],
                    "actes_especes": actes_especes,
                    "paiement_info": paiement_info,
                    "has_frais_supplementaires": prestation.prix_supplementaire > 0,
                    "has_consommations_supplementaires": self._has_consommations_supplementaires(
                        prestation
                    ),
                }
            )

            total_general_paye += paiement_info["total_especes"]

        # Pagination
        items_per_page = min(max(int(request.GET.get("per_page", 25)), 10), 100)
        paginator = Paginator(prestations_with_totals, items_per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "paginator": paginator,
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "items_per_page": items_per_page,
            "total_count": paginator.count,
            "total_general_paye": total_general_paye,
            "medecins": Medecin.objects.filter(prestations__isnull=False).distinct(),
            "patients": Patient.objects.filter(prestations__isnull=False).distinct(),
            "start_date": start_date,
            "end_date": end_date,
            "page_title": "Prestations Espèces - Complètement Réglées",
        }

        return render(request, "facturation_KT/especes_payees.html", context)

    def _has_especes_elements(self, prestation):
        """Vérifie si une prestation a des éléments à payer en espèces"""

        # 1. Actes sans convention ou urgence
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )
        if actes_especes.exists():
            return True

        # 2. Frais supplémentaires
        if prestation.prix_supplementaire > 0:
            return True

        # 3. Consommations supplémentaires
        if self._has_consommations_supplementaires(prestation):
            return True

        return False

    def _has_consommations_supplementaires(self, prestation):
        """Vérifie s'il y a des consommations supplémentaires"""
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    return True
        return False


@method_decorator(
    permission_required("medical.view_paiements_especes", raise_exception=True),
    name="dispatch",
)
class DashboardPaiementsEspecesView(View):
    """Vue dashboard pour un aperçu rapide des paiements espèces - Version adaptée"""

    def get(self, request):
        # Configuration des dates avec ConfigDate
        config, _ = ConfigDate.objects.get_or_create(
            user=request.user,
            page="dashboard_paiements_especes",
            defaults={
                "start_date": date.today() - timedelta(days=30),
                "end_date": date.today(),
            },
        )
         
        # Mise à jour des dates selon les paramètres de la requête
        for param in ("start_date", "end_date"):
            val = request.GET.get(param)
            if val:
                try:
                    setattr(config, param, datetime.strptime(val, "%Y-%m-%d").date())
                except ValueError:
                    pass
        config.save()

        start_date, end_date = config.start_date, config.end_date

        # Récupérer toutes les prestations réalisées dans la période
        prestations_candidates = PrestationKt.objects.filter(
            date_prestation__gte=start_date,
            date_prestation__lte=end_date,
            statut__in=["REALISE", "PAYE"],
        ).prefetch_related("actes_details__consommations", "paiement_especes")

        prestations_attente = []
        prestations_payees = []

        # Classifier les prestations
        for prestation in prestations_candidates:
            if not self._has_especes_elements(prestation):
                continue

            try:
                paiement_especes = prestation.paiement_especes
                if paiement_especes.statut == "COMPLET":
                    prestations_payees.append(prestation)
                else:
                    prestations_attente.append(prestation)
            except PaiementEspecesKt.DoesNotExist:
                prestations_attente.append(prestation)

        # Calculs des totaux
        total_attente = Decimal("0.00")
        total_paye = Decimal("0.00")

        # Pour les prestations en attente
        for prestation in prestations_attente:
            try:
                paiement_especes = prestation.paiement_especes
                total_attente += paiement_especes.montant_restant
            except PaiementEspecesKt.DoesNotExist:
                # Si pas de paiement espèces créé, calculer le total
                total_especes = self._calculate_total_especes_for_dashboard(prestation)
                total_attente += total_especes

        # Pour les prestations payées
        for prestation in prestations_payees:
            if hasattr(prestation, "paiement_especes"):
                total_paye += prestation.paiement_especes.montant_total_du

        # Statistiques supplémentaires avec la plage de dates sélectionnée
        stats_complementaires = self._get_stats_complementaires(start_date, end_date)

        # Calcul du nombre de jours dans la période
        nombre_jours = (end_date - start_date).days + 1

        context = {
            "count_prestations_attente": len(prestations_attente),
            "count_prestations_payees": len(prestations_payees),
            "total_attente": total_attente,
            "total_paye": total_paye,
            "pourcentage_paye": (
                (total_paye / (total_attente + total_paye) * 100)
                if (total_attente + total_paye) > 0
                else 0
            ),
            "prestations_attente_recentes": prestations_attente[:5],
            "prestations_payees_recentes": prestations_payees[:5],
            "start_date": start_date,
            "end_date": end_date,
            "nombre_jours": nombre_jours,
            **stats_complementaires,
        }

        return render(
            request, "facturation_KT/dashboard_paiements_especes.html", context
        )

    def _has_especes_elements(self, prestation):
        """Vérifie si une prestation a des éléments à payer en espèces"""
        

        # 1. Actes sans convention ou urgence
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )
        if actes_especes.exists():
            return True

        # 2. Frais supplémentaires
        if prestation.prix_supplementaire > 0:
            return True

        # 3. Consommations supplémentaires
        for acte_detail in prestation.actes_details.all():
            for conso in acte_detail.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    return True

        return False

    def _calculate_total_especes_for_dashboard(self, prestation):
        """Calcule le total espèces pour une prestation (version optimisée dashboard)"""
        total_especes = Decimal("0.00")
        

        # Actes espèces
        actes_especes = prestation.actes_details.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )

        for pa in actes_especes:
            total_especes += pa.tarif_conventionne

        # Consommations supplémentaires (tous actes)
        for pa in prestation.actes_details.all():
            for conso in pa.consommations.all():
                if conso.quantite_reelle > conso.quantite_defaut:
                    quantite_supp = conso.quantite_reelle - conso.quantite_defaut
                    total_especes += quantite_supp * conso.prix_unitaire

        # Frais supplémentaires
        total_especes += prestation.prix_supplementaire
        return total_especes

    def _get_stats_complementaires(self, start_date, end_date):
        """Récupère des statistiques complémentaires pour le dashboard avec plage de dates"""

        # Statistiques sur les paiements partiels dans la période
        paiements_partiels = PaiementEspecesKt.objects.filter(
            prestation__date_prestation__gte=start_date,
            prestation__date_prestation__lte=end_date,
            statut="EN_COURS",
            montant_paye__gt=0,
        ).distinct()

        # Top 5 des médecins avec le plus de paiements en attente dans la période
        top_medecins_attente = (
            PrestationKt.objects.filter(
                date_prestation__gte=start_date,
                date_prestation__lte=end_date,
            )
            .filter(
                Q(actes_details__convention__isnull=True)
                | Q(actes_details__convention__nom__iexact="urgence")
            )
            .filter(
                Q(paiement_especes__isnull=True)
                | Q(paiement_especes__statut__in=["EN_COURS"])
            )
            .values("medecin__first_name", "medecin__last_name")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        # Paiements par jour dans la période (limité aux 7 derniers jours de la période)
        paiements_par_jour = []
        jours_a_afficher = min(7, (end_date - start_date).days + 1)

        for i in range(jours_a_afficher):
            jour = end_date - timedelta(days=i)
            if jour >= start_date:
                count_jour = TranchePaiementKt.objects.filter(
                    date_paiement__date=jour,
                    paiement_especes__prestation__date_prestation__gte=start_date,
                    paiement_especes__prestation__date_prestation__lte=end_date,
                ).count()
                paiements_par_jour.append(
                    {"jour": jour.strftime("%d/%m"), "count": count_jour}
                )

        # Moyenne des paiements dans la période
        moyenne_paiement = TranchePaiementKt.objects.filter(
            date_paiement__gte=start_date,
            date_paiement__lte=end_date,
            paiement_especes__prestation__date_prestation__gte=start_date,
            paiement_especes__prestation__date_prestation__lte=end_date,
        ).aggregate(avg=Avg("montant"))["avg"] or Decimal("0.00")

        # Évolution quotidienne des montants encaissés
        evolution_quotidienne = []
        for i in range(jours_a_afficher):
            jour = end_date - timedelta(days=i)
            if jour >= start_date:
                montant_jour = TranchePaiementKt.objects.filter(
                    date_paiement__date=jour,
                    paiement_especes__prestation__date_prestation__gte=start_date,
                    paiement_especes__prestation__date_prestation__lte=end_date,
                ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

                evolution_quotidienne.append({
                    "jour": jour.strftime("%d/%m"),
                    "montant": float(montant_jour)
                })

        return {
            "count_paiements_partiels": paiements_partiels.count(),
            "montant_paiements_partiels": sum(
                p.montant_paye for p in paiements_partiels
            ),
            "top_medecins_attente": top_medecins_attente,
            "paiements_par_jour": paiements_par_jour,
            "evolution_quotidienne": evolution_quotidienne,
            "moyenne_paiement": moyenne_paiement,
        }
