# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
from .models import Patient
import json


def patient_list(request):
    """Liste des patients avec recherche et pagination"""
    search_query = request.GET.get("search", "")
    filter_active = request.GET.get("active", "all")

    # Base queryset
    patients = Patient.objects.all()

    # Filtres
    if search_query:
        patients = patients.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(social_security_number__icontains=search_query)
            | Q(phone_number__icontains=search_query)
        )

    if filter_active == "active":
        patients = patients.filter(is_active=True)
    elif filter_active == "inactive":
        patients = patients.filter(is_active=False)

    # Pagination
    paginator = Paginator(patients.order_by("-created_at"), 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "patients": page_obj,
        "search_query": search_query,
        "filter_active": filter_active,
        "total_patients": patients.count(),
    }

    return render(request, "patient_liste.html", context)


def patient_detail(request, patient_id):
    """Détail d'un patient"""
    patient = get_object_or_404(Patient, id=patient_id)

    context = {
        "patient": patient,
        "current_admission": patient.current_admission,
        "total_admissions": patient.total_hospitalizations,
        "total_days": patient.total_hospitalization_days,
        "total_costs": patient.total_medical_costs,
    }

    return render(request, "patient_detail.html", context)

# views.py - Partie modifiée
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
from .models import Patient
import json


def patient_create(request):
    """Créer un nouveau patient"""
    if request.method == "GET":
        context = {
            "action": "create",
            "title": "Nouveau Patient",
            "gender_choices": Patient.GENDER_CHOICES,
            "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
        }
        return render(request, "patient_form.html", context)

    elif request.method == "POST":
        try:
            # Récupération des données du POST
            data = {
                "first_name": request.POST.get("first_name", "").strip(),
                "last_name": request.POST.get("last_name", "").strip(),
                "gender": request.POST.get("gender"),
                "date_of_birth": request.POST.get("date_of_birth") or None,
                "place_of_birth": request.POST.get("place_of_birth", "").strip(),
                "social_security_number": request.POST.get(
                    "social_security_number", ""
                ).strip(),
                "nom_de_assure": request.POST.get("nom_de_assure", "").strip(),
                "securite_sociale": request.POST.get("securite_sociale"),
                "phone_number": request.POST.get("phone_number", "").strip(),
                "email": request.POST.get("email", "").strip(),
                "address": request.POST.get("address", "").strip(),
            }

            # Validation des champs obligatoires
            errors = []
            if not data["first_name"]:
                errors.append("Le prénom est obligatoire")
            if not data["last_name"]:
                errors.append("Le nom est obligatoire")
            if not data["gender"]:
                errors.append("Le genre est obligatoire")

            # Validation du numéro de sécurité sociale unique
            if data["social_security_number"]:
                if Patient.objects.filter(
                    social_security_number=data["social_security_number"]
                ).exists():
                    errors.append("Ce numéro de sécurité sociale existe déjà")

            # Validation de l'email
            if data["email"]:
                from django.core.validators import validate_email
                from django.core.exceptions import ValidationError

                try:
                    validate_email(data["email"])
                except ValidationError:
                    errors.append("Format d'email invalide")

            if errors:
                context = {
                    "action": "create",
                    "title": "Nouveau Patient",
                    "errors": errors,
                    "data": data,
                    "gender_choices": Patient.GENDER_CHOICES,
                    "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
                }
                return render(request, "patient_form.html", context)

            # Nettoyage des données vides
            cleaned_data = {}
            for key, value in data.items():
                if value == "":
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = value

            # Conversion de la date de naissance
            if cleaned_data["date_of_birth"]:
                try:
                    cleaned_data["date_of_birth"] = datetime.strptime(
                        cleaned_data["date_of_birth"], "%Y-%m-%d"
                    ).date()
                except ValueError:
                    errors.append("Format de date invalide")
                    context = {
                        "action": "create",
                        "title": "Nouveau Patient",
                        "errors": errors,
                        "data": data,
                        "gender_choices": Patient.GENDER_CHOICES,
                        "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
                    }
                    return render(request, "patient_form.html", context)

            # Création du patient
            patient = Patient.objects.create(**cleaned_data)

            messages.success(
                request, f"Patient {patient.nom_complet} créé avec succès!"
            )
            return redirect("patients:patient_detail", patient_id=patient.id)

        except Exception as e:
            messages.error(request, f"Erreur lors de la création: {str(e)}")
            context = {
                "action": "create",
                "title": "Nouveau Patient",
                "errors": [str(e)],
                "data": data if "data" in locals() else {},
                "gender_choices": Patient.GENDER_CHOICES,
                "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
            }
            return render(request, "patient_form.html", context)


def patient_update(request, patient_id):
    """Modifier un patient"""
    patient = get_object_or_404(Patient, id=patient_id)

    if request.method == "GET":
        context = {
            "action": "update",
            "title": f"Modifier {patient.nom_complet}",
            "patient": patient,
            "gender_choices": Patient.GENDER_CHOICES,
            "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
        }
        return render(request, "patient_form.html", context)

    elif request.method == "POST":
        try:
            # Récupération des données du POST
            data = {
                "first_name": request.POST.get("first_name", "").strip(),
                "last_name": request.POST.get("last_name", "").strip(),
                "gender": request.POST.get("gender"),
                "date_of_birth": request.POST.get("date_of_birth") or None,
                "place_of_birth": request.POST.get("place_of_birth", "").strip(),
                "social_security_number": request.POST.get(
                    "social_security_number", ""
                ).strip(),
                "nom_de_assure": request.POST.get("nom_de_assure", "").strip(),
                "securite_sociale": request.POST.get("securite_sociale"),
                "phone_number": request.POST.get("phone_number", "").strip(),
                "email": request.POST.get("email", "").strip(),
                "address": request.POST.get("address", "").strip(),
            }

            # Validation des champs obligatoires
            errors = []
            if not data["first_name"]:
                errors.append("Le prénom est obligatoire")
            if not data["last_name"]:
                errors.append("Le nom est obligatoire")
            if not data["gender"]:
                errors.append("Le genre est obligatoire")

            # Validation du numéro de sécurité sociale unique (exclure le patient actuel)
            if data["social_security_number"]:
                existing = Patient.objects.filter(
                    social_security_number=data["social_security_number"]
                ).exclude(id=patient.id)
                if existing.exists():
                    errors.append("Ce numéro de sécurité sociale existe déjà")

            # Validation de l'email
            if data["email"]:
                from django.core.validators import validate_email
                from django.core.exceptions import ValidationError

                try:
                    validate_email(data["email"])
                except ValidationError:
                    errors.append("Format d'email invalide")

            if errors:
                context = {
                    "action": "update",
                    "title": f"Modifier {patient.nom_complet}",
                    "patient": patient,
                    "errors": errors,
                    "data": data,
                    "gender_choices": Patient.GENDER_CHOICES,
                    "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
                }
                return render(request, "patient_form.html", context)

            # Nettoyage des données vides
            for key, value in data.items():
                if value == "":
                    setattr(patient, key, None)
                else:
                    if key == "date_of_birth" and value:
                        try:
                            value = datetime.strptime(value, "%Y-%m-%d").date()
                        except ValueError:
                            errors.append("Format de date invalide")
                            context = {
                                "action": "update",
                                "title": f"Modifier {patient.nom_complet}",
                                "patient": patient,
                                "errors": errors,
                                "data": data,
                                "gender_choices": Patient.GENDER_CHOICES,
                                "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
                            }
                            return render(
                                request, "patient_form.html", context
                            )
                    setattr(patient, key, value)

            patient.save()

            messages.success(
                request, f"Patient {patient.nom_complet} modifié avec succès!"
            )
            return redirect("patients:patient_detail", patient_id=patient.id)

        except Exception as e:
            messages.error(request, f"Erreur lors de la modification: {str(e)}")
            context = {
                "action": "update",
                "title": f"Modifier {patient.nom_complet}",
                "patient": patient,
                "errors": [str(e)],
                "data": data if "data" in locals() else {},
                "gender_choices": Patient.GENDER_CHOICES,
                "securite_sociale_choices": Patient.SECURITE_SOCIALE_CHOICES,
            }
            return render(request, "patient_form.html", context)


@require_http_methods(["POST"])
def patient_delete(request, patient_id):
    """Supprimer un patient (soft delete)"""
    patient = get_object_or_404(Patient, id=patient_id)

    try:
        patient.delete()  # Utilise la méthode soft delete du modèle
        messages.success(
            request, f"Patient {patient.nom_complet} supprimé avec succès!"
        )
    except Exception as e:
        messages.error(request, f"Erreur lors de la suppression: {str(e)}")

    return redirect("patients:patient_list")


@require_http_methods(["POST"])
def patient_toggle_status(request, patient_id):
    """Activer/Désactiver un patient"""
    patient = get_object_or_404(Patient, id=patient_id)

    try:
        patient.is_active = not patient.is_active
        patient.save()

        status = "activé" if patient.is_active else "désactivé"
        messages.success(
            request, f"Patient {patient.nom_complet} {status} avec succès!"
        )
    except Exception as e:
        messages.error(request, f"Erreur lors du changement de statut: {str(e)}")

    return redirect("patients:patient_detail", patient_id=patient.id)


def patient_search_api(request):
    """API de recherche pour l'autocomplete"""
    query = request.GET.get("q", "")
    if len(query) < 2:
        return JsonResponse({"results": []})

    patients = Patient.objects.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(social_security_number__icontains=query),
        is_active=True,
    )[:10]

    results = []
    for patient in patients:
        results.append(
            {
                "id": patient.id,
                "text": f"{patient.nom_complet} - {patient.social_security_number or 'N/A'}",
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "social_security_number": patient.social_security_number,
                "age": patient.age,
            }
        )

    return JsonResponse({"results": results})
