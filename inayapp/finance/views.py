# finance/views.py
import copy
import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from accueil.models import ConfigDate
from audit.decorators import audit_view
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models, transaction
from django.db.models import (Count, DecimalField, ExpressionWrapper, F,
                              OuterRef, Prefetch, Q, Subquery, Sum, Value)
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.safestring import mark_safe
from django.views import View
from finance.models import (Convention, Decharges, Payments,
                            PrixSupplementaireConfig, TarifActe,
                            TarifActeConvention)
from medecin.models import Medecin
from medical.models import (Acte, ActeProduit, Prestation, PrestationActe,
                            PrestationAudit)
from medical.models.actes import ActeProduit
from num2words import num2words
from patients.models import Patient
from pharmacies.models import ConsommationProduit, Produit
from rh.models import Personnel, Planning
from utils.pdf import render_to_pdf
from utils.utils import services_autorises

from .forms import DechargeForm, PaymentForm
from .models import Decharges, Payments


# decharge planning
@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def add_decharge_multiple(request):
    if request.method != "POST":
        messages.error(request, "Méthode non autorisée.")
        return redirect(reverse("planning"))
    employee_ids = request.POST.getlist("employeurs")
    start_date_str = request.POST.get("start_date", "").strip()
    end_date_str = request.POST.get("end_date", "").strip()
    date_str = request.POST.get("date", "").strip()

    if not employee_ids or not date_str:
        messages.error(request, "Tous les champs sont requis.")
        return redirect(reverse("planning"))

    date_obj = parse_date(date_str)
    start_date_obj = parse_date(start_date_str)
    end_date_obj = parse_date(end_date_str)

    errors = []

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
                    emp_id_int = int(emp_id)
                except ValueError:
                    errors.append(f"Identifiant invalide pour l'employé : {emp_id}")
                    continue

                # Récupération du nom complet de l'employé
                try:
                    employee_obj = Personnel.objects.get(pk=emp_id_int)
                    full_name = employee_obj.nom_prenom
                except Personnel.DoesNotExist:
                    full_name = "Inconnu"
                    employee_obj = None

                # Filtrage des plannings pour l'employé sur la période définie
                # et qui n'ont pas encore de décharge (decharge_created_at est null)
                plannings = Planning.objects.filter(
                    employee_id=emp_id_int,
                    shift_date__range=(start_date_obj, end_date_obj),
                    id_decharge__isnull=True,
                )

                aggregation = plannings.aggregate(
                    total_salary=Sum(
                        F("prix") + F("prix_acte"), output_field=DecimalField()
                    )
                )
                total_salary = aggregation["total_salary"] or Decimal("0.00")

                if total_salary <= 0:
                    errors.append(f"L'employé {full_name} n'a pas de salaire positif.")
                    continue

                dossiers_list = []
                # Construction des informations de dossiers pour chaque planning filtré
                for p in plannings.select_related("id_service", "employee"):
                    service_name = (
                        p.id_service.name if p.id_service else "Inconnu"
                    )
                    dossier = f"{service_name} - {p.shift_date} - {p.shift} - {p.prix}"
                    if p.prix_acte and p.prix_acte != 0:
                        dossier += f" - Actes {p.prix_acte}"
                    dossiers_list.append(dossier)

                # Création de la décharge et récupération de l'instance
                decharge = Decharges.objects.create(
                    name=full_name,
                    amount=total_salary,
                    date=date_obj,
                    note="\n".join(dossiers_list),
                    created_at=timezone.now(),
                    id_created_par=request.user,
                    id_employe=emp_id_int,
                )

                # Mise à jour des plannings concernés avec l’ID de la décharge
                plannings.update(
                    id_decharge=decharge.id_decharge,
                )

            if errors:
                for err in errors:
                    messages.error(request, err)
            else:
                messages.success(request, "Décharges ajoutées avec succès.")

    except Exception as e:
        messages.error(
            request, "Une erreur est survenue lors de l'ajout des décharges."
        )

    return redirect(reverse("planning"))


@login_required
def decharge_list(request):
    decharges = (
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

    return render(
        request, "decharges/decharges_list.html", {"decharges": decharges}
    )


@login_required
def decharge_settled(request):
    decharges = (
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

    return render(
        request, "decharges/decharges_settled.html", {"decharges": decharges}
    )


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
def situation_medecins_list(request):
    # 1. Honoraires (incluant prix supplémentaire médecin)
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
        Payments.objects
        .filter(id_decharge__medecin=OuterRef('pk'))
        .values('id_decharge__medecin')
        .annotate(total=Sum('payment'))
        .values('total')
    )

    # 3. Décharge totales
    decharge_sq = (
        Decharges.objects
        .filter(medecin=OuterRef('pk'))
        .values('medecin')
        .annotate(total=Sum('amount'))
        .values('total')
    )

    # 4. Préfetch des décharge + sommes de paiements par décharge
    decharges_non_reglees_qs = (
        Decharges.objects
        # On exclut d’abord toute décharge qui contient au moins un acte rattaché à une prestation planifiée
        .exclude(prestation_actes__prestation__statut='planifie')
        .annotate(
            total_paie=Coalesce(Sum('payments__payment'), Value(0), output_field=DecimalField())
        )
        .annotate(
            solde=ExpressionWrapper(F('amount') - F('total_paie'), output_field=DecimalField())
        )
        # Puis on ne garde que celles dont le solde reste positif
        .filter(solde__gt=0)
    )


    # 5. Query principal
    medecins = (
        Medecin.objects
        .prefetch_related(
            Prefetch(
                'decharges',
                queryset=decharges_non_reglees_qs,
                to_attr='decharges_non_reglees'
            )
        )
        .annotate(
            total_honoraires=Coalesce(
                Subquery(honoraire_sq), Value(Decimal('0.00')), output_field=DecimalField()
            ),
            total_paiements=Coalesce(
                Subquery(paiement_sq), Value(Decimal('0.00')), output_field=DecimalField()
            ),
            total_decharges=Coalesce(
                Subquery(decharge_sq), Value(Decimal('0.00')), output_field=DecimalField()
            ),
        )
        .annotate(
            reste_avec_decharge=ExpressionWrapper(
                F('total_honoraires') - F('total_paiements'),
                output_field=DecimalField()
            ),
            reste_sans_decharge=ExpressionWrapper(
                F('total_honoraires') - F('total_decharges'),
                output_field=DecimalField()
            ),
        )
        .order_by('-total_honoraires')
    )

    # 6. Calcul des montants et comptes non réglés en Python
    for med in medecins:
        # total et count des décharges non réglées
        total_non_regle = sum(d.solde for d in med.decharges_non_reglees)
        count_non_regle = len(med.decharges_non_reglees)
        med.total_non_regle = total_non_regle
        med.count_non_regle = count_non_regle

    # 7. Totaux globaux
    totals = {
        'global_honoraires': sum(m.total_honoraires for m in medecins),
        'global_paiements': sum(m.total_paiements for m in medecins),
        'global_decharges': sum(m.total_decharges for m in medecins),
        'global_reste_avec': sum(m.reste_avec_decharge for m in medecins),
        'global_reste_sans': sum(m.reste_sans_decharge for m in medecins),
        'global_non_regle': sum(m.total_non_regle for m in medecins),
    }

    return render(
        request,
        'situation_medecins_list.html',
        {
            'medecins': medecins,
            **totals
        }
    )


@audit_view
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

    prestation_query = Prestation.objects.filter(medecin=medecin)

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
        "acte_labels": [a["acte__libelle"] or "Acte inconnu" for a in actes_data],
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

    return render(request, "situation.html", context)


@audit_view
def create_decharge_medecin(request, medecin_id):
    medecin = get_object_or_404(Medecin, pk=medecin_id)

    prestations_non_dechargees = (
        PrestationActe.objects.filter(prestation__medecin=medecin)
        .exclude(prestation__statut="planifie")
        .exclude(decharges__isnull=False)
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
                f"Acte: {prestation.acte.libelle} ({prestation.acte.code})",
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
def gestion_convention_accorde(request):
    # --- Récupération / mise à jour de la config date
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="convention_accorde",
        defaults={"start_date": date.today(), "end_date": date.today()},
    )

    # Mise à jour de la config si des paramètres sont fournis
    for param in ("start_date", "end_date"):
        val = request.GET.get(param)
        if val:
            try:
                setattr(config, param, datetime.strptime(val, "%Y-%m-%d").date())
            except ValueError:
                pass
    config.save()

    # Utilisation des dates de la config
    start_date, end_date = (config.start_date, config.end_date)

    # Base queryset
    prestation_actes = PrestationActe.objects.filter(
        convention__isnull=False
    ).select_related("prestation", "acte", "convention")

    # Filters
    status = request.GET.get("status")
    medecin_id = request.GET.get("medecin")
    patient_id = request.GET.get("patient")

    # Apply filters
    if status == "en_attente":
        prestation_actes = prestation_actes.filter(convention_accordee__isnull=True)
    elif status == "accorde":
        prestation_actes = prestation_actes.filter(convention_accordee=True)
    elif status == "non_accorde":
        prestation_actes = prestation_actes.filter(convention_accordee=False)

    # Filtrage par date (utilise les dates de la config)
    if start_date and end_date:
        prestation_actes = prestation_actes.filter(
            prestation__date_prestation__range=[start_date, end_date]
        )
    elif start_date:
        prestation_actes = prestation_actes.filter(
            prestation__date_prestation__gte=start_date
        )
    elif end_date:
        prestation_actes = prestation_actes.filter(
            prestation__date_prestation__lte=end_date
        )

    if medecin_id:
        prestation_actes = prestation_actes.filter(prestation__medecin_id=medecin_id)
    if patient_id:
        prestation_actes = prestation_actes.filter(prestation__patient_id=patient_id)

    # Get distinct medecins and patients for filters
    medecins = Medecin.objects.filter(
        prestations__actes_details__convention__isnull=False
    ).distinct()
    patients = Patient.objects.filter(
        prestations__actes_details__convention__isnull=False
    ).distinct()

    context = {
        "prestation_actes": prestation_actes,
        "medecins": medecins,
        "patients": patients,
        "current_status": status,
        "start_date": start_date,  # Utilise les dates de la config
        "end_date": end_date,  # Utilise les dates de la config
        "current_medecin": medecin_id,
        "current_patient": patient_id,
    }

    return render(request, "gestion_convention_accorde.html", context)


@audit_view
@login_required
def update_convention_status(request, pk):
    if not request.user.has_perm("medical.change_prestationacte"):
        return JsonResponse({"error": "Permission refusée"}, status=403)

    prestation_acte = get_object_or_404(PrestationActe, pk=pk)
    action = request.GET.get("action")

    response_data = {
        "status": "success",
        "new_status": None,
        "message": "",
        "stats": {},
    }

    try:
        if action == "approve":
            prestation_acte.convention_accordee = True
            response_data["message"] = (
                f"Convention {prestation_acte.convention} approuvée"
            )
        elif action == "reject":
            prestation_acte.convention_accordee = False
            response_data["message"] = (
                f"Convention {prestation_acte.convention} refusée"
            )
        elif action == "reset":
            prestation_acte.convention_accordee = None
            response_data["message"] = "Statut convention réinitialisé"
        else:
            raise ValueError("Action invalide")

        prestation_acte.save()
        response_data["new_status"] = prestation_acte.convention_accordee

        # Mise à jour des stats
        qs = PrestationActe.objects.filter(convention__isnull=False)
        response_data["stats"] = {
            "total": qs.count(),
            "en_attente": qs.filter(convention_accordee__isnull=True).count(),
            "accorde": qs.filter(convention_accordee=True).count(),
            "refuse": qs.filter(convention_accordee=False).count(),
        }

    except Exception as e:
        response_data = {"status": "error", "message": str(e)}

    return (
        JsonResponse(response_data)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest"
        else redirect("gestion_convention_accorde")
    )


# medical/views/paiements.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.db import transaction
from decimal import Decimal
from medical.models import Prestation
from .models import BonDePaiement
from .forms import BonDePaiementForm


@login_required
def paiements_especes(request):
    # Filtrer les prestations éligibles
    prestations = (
        Prestation.objects.filter(
            Q(statut="REALISE")
            & (
                Q(prix_supplementaire__gt=0)
                | Q(actes_details__convention__isnull=True)
                | Q(actes_details__convention_accordee=False)
                | Q(
                    actes_details__consommations__quantite_reelle__gt=F(
                        "actes_details__consommations__quantite_defaut"
                    )
                )
            )
        )
        .distinct()
        .prefetch_related("patient", "actes_details")
    )

    # Calcul du reste à payer pour chaque prestation
    for p in prestations:
        p.total_paiements = p.bons_de_paiement.aggregate(total=Sum("montant"))[
            "total"
        ] or Decimal("0.00")
        p.reste_a_payer = p.prix_total - p.total_paiements

    return render(request, "BonPaiement/liste.html", {"prestations": prestations})


@login_required
@transaction.atomic
def creer_bon_paiement(request, prestation_id):
    prestation = get_object_or_404(Prestation, id=prestation_id)

    # Calcul du reste à payer
    total_paiements = prestation.bons_de_paiement.aggregate(total=Sum("montant"))[
        "total"
    ] or Decimal("0.00")
    reste = prestation.prix_total - total_paiements

    if request.method == "POST":
        form = BonDePaiementForm(request.POST)
        if form.is_valid():
            bon = form.save(commit=False)
            bon.prestation = prestation
            bon.encaisse_par = request.user

            # Validation du montant
            if bon.montant > reste:
                form.add_error("montant", f"Le montant ne peut excéder {reste}€")
            else:
                bon.save()

                # Mettre à jour le statut de la prestation si complètement payée
                if bon.montant >= reste:
                    prestation.statut = "PAYE"
                    prestation.save()

                return redirect("paiements_especes")
    else:
        form = BonDePaiementForm(initial={"montant": reste})

    return render(
        request,
        "BonPaiement/creer_bon.html",
        {"form": form, "prestation": prestation, "reste": reste},
    )
