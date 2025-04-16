from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import DecimalField, F, Sum
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils.dateparse import parse_date
from rh.models import Personnel, Planning

from .forms import DechargeForm, PaymentForm
from .models import Decharges, Payments


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def add_decharge_multiple(request):
    if request.method != "POST":
        messages.error(request, "Méthode non autorisée.")
        return redirect(reverse("planning"))

    employee_ids = request.POST.getlist("employeurs")
    start_date_str = request.POST.get("start_date", "").strip()
    end_date_str = request.POST.get("end_date", "").strip()
    date_str = request.POST.get("date", "").strip()
    print(
        f"Received employee_ids: {employee_ids}, start_date: {start_date_str}, end_date: {end_date_str}, date: {date_str}"
    )

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
                    decharge_created_at__isnull=True,
                )

                aggregation = plannings.aggregate(
                    total_salary=Sum(
                        F("prix") + F("prix_acte"), output_field=DecimalField()
                    )
                )
                total_salary = aggregation["total_salary"] or Decimal("0.00")
                print(f"Total Salary for {full_name}: {total_salary}")

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
                        f"{service_name} - {p.shift_date} - {p.shift_type} - {p.prix}"
                    )
                    if p.prix_acte and p.prix_acte != 0:
                        dossier += f" - Actes {p.prix_acte}"
                    dossiers_list.append(dossier)

                # Mise à jour des plannings concernés avec les informations de décharge
                plannings.update(
                    decharge_id_created_par=personnel_user,
                    decharge_created_at=datetime.now(),
                )

                # Création de la décharge
                Decharges.objects.create(
                    name=full_name,
                    amount=total_salary,
                    date=date_obj,
                    note="\n".join(dossiers_list),
                    created_at=datetime.now(),
                    id_created_par=request.user,
                    id_employe=emp_id_int,
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
def manage_decharges_payments(request):
    # Initialisation des formulaires
    if request.method == "POST":
        if "submit_decharge" in request.POST:
            decharge_form = DechargeForm(request.POST)
            payment_form = PaymentForm()  # Formulaire vide pour paiement
            if decharge_form.is_valid():
                decharge = decharge_form.save(commit=False)
                # Remplissage automatique de certains champs
                decharge.id_created_par = request.user
                decharge.created_at = datetime.now()
                decharge.save()
                messages.success(request, "Décharge ajoutée avec succès.")
                return redirect("manage_decharges_payments")
            else:
                messages.error(request, "Erreur dans le formulaire de décharge.")
        elif "submit_payment" in request.POST:
            payment_form = PaymentForm(request.POST)
            decharge_form = DechargeForm()  # Formulaire vide pour décharge
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                # Si aucun temps de paiement n'est renseigné, on le définit automatiquement
                if not payment.time_payment:
                    payment.time_payment = datetime.now()
                payment.save()
                messages.success(request, "Paiement ajouté avec succès.")
                return redirect("manage_decharges_payments")
            else:
                messages.error(request, "Erreur dans le formulaire de paiement.")
    else:
        decharge_form = DechargeForm()
        payment_form = PaymentForm()

    # Récupération de la liste des décharges et paiements
    decharges = Decharges.objects.all().order_by("-created_at")
    payments = Payments.objects.all().order_by("-time_payment")

    context = {
        "decharge_form": decharge_form,
        "payment_form": payment_form,
        "decharges": decharges,
        "payments": payments,
    }
    return render(request, "finance/decharges_payments.html", context)
