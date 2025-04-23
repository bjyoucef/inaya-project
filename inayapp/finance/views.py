from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from num2words import num2words
from rh.models import Personnel, Planning

from .forms import DechargeForm, PaymentForm
from .models import Decharges, Payments
from utils.pdf import render_to_pdf


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
                        p.id_service.service_name if p.id_service else "Inconnu"
                    )
                    dossier = (
                        f"{service_name} - {p.shift_date} - {p.shift} - {p.prix}"
                    )
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
        print(f"Erreur : {e}")

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
        request, "finance/decharges/decharges_list.html", {"decharges": decharges}
    )


@login_required
def decharge_settled(request):
    decharges = ( Decharges.objects.annotate(
        total_payments=Coalesce(
            Sum("payments__payment", output_field=models.DecimalField()),
            Value(0, output_field=models.DecimalField())
    )).annotate(
        balance=ExpressionWrapper(
            F("amount") - F("total_payments"),
            output_field=models.DecimalField(max_digits=10, decimal_places=2)
        )
    ).filter(balance=0).order_by("-date"))

    return render(
        request, "finance/decharges/decharges_settled.html", {"decharges": decharges}
    )

@login_required
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
        "finance/decharges/decharges_detail.html",
        {
            "decharge": decharge,
            "payments": payments,
            "form": form,
            "total_payments": total_payments,
            "balance": balance,
        },
    )


@login_required
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
    return render(request, "finance/decharges/decharges_form.html", {"form": form})


@login_required
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
    return render(request, "finance/decharges/decharges_form.html", {"form": form})


@login_required
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
        "finance/decharges/decharges_confirm_delete.html",
        {"decharge": decharge},
    )


@login_required
def payment_delete(request, pk):
    payment = get_object_or_404(Payments, pk=pk)
    decharge_pk = payment.id_decharge.pk
    if request.method == "POST":
        payment.delete()
        messages.success(request, "Paiement supprimé avec succès")
        return redirect("decharge_detail", pk=decharge_pk)
    return render(
        request,
        "finance/decharges/decharges_confirm_payment_delete.html",
        {"payment": payment},
    )


@login_required
def export_decharge_pdf(request, decharge_id):
    decharge = get_object_or_404(Decharges, pk=decharge_id)

    amount_in_words = num2words(decharge.amount, lang="fr").capitalize() + " dinars"

    context = {
        "id": decharge.id_decharge,
        "date": decharge.date.strftime("%d/%m/%Y") if decharge.date else "",
        "name": decharge.name,
        "amount": decharge.amount,
        "amount_in_words": amount_in_words,
        "dossiers": decharge.note.split("\n") if decharge.note else [],
    }

    pdf_response = render_to_pdf("finance/decharges/decharge_pdf.html", context)
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

    return render(request, "finance/decharges/decharge_pdf.html", context)
