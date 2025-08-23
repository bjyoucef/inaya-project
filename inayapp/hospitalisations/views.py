# hospitalisation/views.py
import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from medecin.models import Medecin
from medical.models import Service
from patients.models import Patient
from rh.models import Personnel

from .models import (Admission, AdmissionRequest, Bed, Room, StayHistory,
                     TransferHistory)


@login_required
def floor_plan_centralized(request, service_id):
    """Vue centralisée pour le plan d'étage avec toutes les fonctionnalités"""
    service = get_object_or_404(Service, id=service_id)

    # Récupérer toutes les chambres du service avec leurs lits
    rooms = (
        Room.objects.filter(service=service, is_active=True)
        .prefetch_related("beds__admissions__patient")
        .order_by("floor", "room_number")
    )



    # Récupérer les demandes d'admission en attente pour ce service
    waiting_requests = (
        AdmissionRequest.objects.filter(service=service, status="waiting")
        .select_related("patient", "referring_doctor")
        .order_by("request_date")
    )

    # Récupérer toutes les demandes d'admission pour le modal
    all_admission_requests = (
        AdmissionRequest.objects.filter(service=service)
        .select_related("patient", "referring_doctor", "created_by")
        .order_by("-request_date")[:100]  # Limiter pour les performances
    )

    # Récupérer les admissions actuelles
    current_admissions = (
        Admission.objects.filter(
            bed__room__service=service, is_active=True, discharge_date__isnull=True
        )
        .select_related("patient", "bed__room", "attending_doctor")
        .order_by("admission_date")
    )

    # Calculer la durée de séjour pour chaque admission
    for admission in current_admissions:
        admission.length_of_stay_days = admission.length_of_stay
        admission.estimated_cost = admission.calculate_total_cost()

    # Récupérer l'historique des admissions (3 derniers mois)
    three_months_ago = timezone.now() - timedelta(days=90)
    admission_history = (
        Admission.objects.filter(
            bed__room__service=service, admission_date__gte=three_months_ago
        )
        .select_related("patient", "bed__room", "attending_doctor")
        .order_by("-admission_date")[:50]  # Limiter pour les performances
    )

    # Calculer les coûts pour l'historique
    total_revenue = 0
    total_stays_days = 0
    for admission in admission_history:
        admission.length_of_stay_days = admission.length_of_stay
        admission.calculated_total_cost = admission.calculate_total_cost()
        total_revenue += admission.calculated_total_cost
        total_stays_days += admission.length_of_stay

    # Calculer la durée moyenne de séjour
    average_stay = total_stays_days / len(admission_history) if admission_history else 0

    # Calculer les statistiques globales
    all_beds = Bed.objects.filter(room__service=service, is_active=True)
    total_beds = all_beds.count()
    occupied_beds = all_beds.filter(is_occupied=True).count()
    maintenance_beds = all_beds.filter(maintenance_required=True).count()
    available_beds = total_beds - occupied_beds - maintenance_beds

    occupancy_rate = (
        round((occupied_beds / total_beds) * 100, 1) if total_beds > 0 else 0
    )

    stats = {
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "maintenance_beds": maintenance_beds,
        "occupancy_rate": occupancy_rate,
    }

    # Récupérer les données pour les formulaires
    patients = Patient.objects.filter(is_active=True).order_by(
        "last_name", "first_name"
    )[
        :100
    ]  # Limiter pour les performances
    services = Service.objects.filter(est_hospitalier=True).order_by("name")
    doctors = Medecin.objects.select_related("personnel__user").all()[:50]

    context = {
        "service": service,
        "rooms": rooms,
        "waiting_requests": waiting_requests,
        "admission_requests": all_admission_requests,
        "current_admissions": current_admissions,
        "admission_history": admission_history,
        "total_revenue": total_revenue,
        "average_stay": round(average_stay, 1),
        "stats": stats,
        "patients": patients,
        "services": services,
        "doctors": doctors,
    }

    return render(request, "floor_plan_centralized.html", context)


@login_required
def add_admission_request(request):
    """Créer une nouvelle demande d'admission"""
    if request.method == "POST":
        try:
            patient_id = request.POST.get("patient_id")
            service_id = request.POST.get("service_id")
            referring_doctor_id = request.POST.get("referring_doctor_id")
            reason = request.POST.get("reason")
            diagnosis = request.POST.get("diagnosis", "")
            notes = request.POST.get("notes", "")
            estimated_duration = request.POST.get("estimated_duration")

            # Validation des champs obligatoires
            if not all([patient_id, service_id, reason]):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Patient, service et motif sont obligatoires",
                    }
                )

            patient = get_object_or_404(Patient, id=patient_id)
            service = get_object_or_404(Service, id=service_id)

            referring_doctor = None
            if referring_doctor_id:
                referring_doctor = get_object_or_404(Medecin, id=referring_doctor_id)

            # Récupérer le personnel connecté
            try:
                created_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                created_by = None

            # Créer la demande d'admission
            admission_request = AdmissionRequest.objects.create(
                patient=patient,
                service=service,
                referring_doctor=referring_doctor,
                reason=reason,
                diagnosis=diagnosis,
                notes=notes,
                estimated_duration=(
                    int(estimated_duration) if estimated_duration else None
                ),
                created_by=created_by,
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": "Demande d'admission créée avec succès",
                    "request_id": admission_request.id,
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})


@login_required
@csrf_exempt
def admit_patient(request):
    """API endpoint pour admettre un patient via drag & drop"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        data = json.loads(request.body)
        request_id = data.get("request_id")
        bed_id = data.get("bed_id")

        if not request_id or not bed_id:
            return JsonResponse({"success": False, "error": "Données manquantes"})

        with transaction.atomic():
            # Récupérer la demande d'admission
            admission_request = get_object_or_404(AdmissionRequest, id=request_id)

            # Vérifier que la demande est en attente
            if admission_request.status != "waiting":
                return JsonResponse(
                    {"success": False, "error": "Cette demande n'est plus en attente"}
                )

            # Récupérer le lit
            bed = get_object_or_404(Bed, id=bed_id)

            # Vérifier que le lit est disponible
            if bed.is_occupied or bed.maintenance_required:
                return JsonResponse(
                    {"success": False, "error": "Ce lit n'est pas disponible"}
                )

            # Vérifier que le lit est dans le bon service
            if bed.room.service != admission_request.service:
                return JsonResponse(
                    {"success": False, "error": "Ce lit n'est pas dans le bon service"}
                )

            # Récupérer le personnel connecté
            try:
                created_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                created_by = None

            # Créer l'admission
            admission = Admission.objects.create(
                patient=admission_request.patient,
                bed=bed,
                admission_request=admission_request,
                attending_doctor=admission_request.referring_doctor,
                diagnosis=admission_request.diagnosis or admission_request.reason,
                treatment_plan=admission_request.notes or "",
                created_by=created_by,
            )

            return JsonResponse(
                {
                    "success": True,
                    "patient_name": f"{admission_request.patient.last_name} {admission_request.patient.first_name}",
                    "admission_id": admission.id,
                }
            )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

# Modification de la fonction transfer_patient dans hospitalisation/views.py


@login_required
@csrf_exempt
def transfer_patient(request):
    """API pour transférer un patient d'un lit à un autre avec gestion des coûts par séjour"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        data = json.loads(request.body)
        admission_id = data.get("admission_id")
        new_bed_id = data.get("new_bed_id")
        reason = data.get("reason", "Transfert initié par l'administration")

        if not admission_id or not new_bed_id:
            return JsonResponse({"success": False, "error": "Données manquantes"})

        with transaction.atomic():
            # Récupérer l'admission actuelle avec des critères plus flexibles
            try:
                current_admission = Admission.objects.get(id=admission_id)

                # Vérifications supplémentaires
                if not current_admission.is_active:
                    return JsonResponse(
                        {"success": False, "error": "Cette admission n'est plus active"}
                    )

                if current_admission.discharge_date:
                    return JsonResponse(
                        {"success": False, "error": "Ce patient est déjà sorti"}
                    )

                # Si ce n'est pas le lit actuel, chercher l'admission avec le lit actuel
                if not current_admission.is_current_bed:
                    # Chercher l'admission actuelle pour ce patient
                    patient = current_admission.patient
                    actual_current_admission = Admission.objects.filter(
                        patient=patient,
                        is_active=True,
                        is_current_bed=True,
                        discharge_date__isnull=True,
                    ).first()

                    if actual_current_admission:
                        current_admission = actual_current_admission
                    else:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": "Aucune admission active trouvée pour ce patient",
                            }
                        )

            except Admission.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Admission non trouvée"}
                )

            # Trouver l'admission principale (parent)
            main_admission = current_admission.parent_admission or current_admission

            old_bed = current_admission.bed
            patient = current_admission.patient

            # Vérifier le nouveau lit
            new_bed = get_object_or_404(Bed, id=new_bed_id)
            if new_bed.is_occupied or new_bed.maintenance_required:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Le lit de destination n'est pas disponible",
                    }
                )

            if new_bed.room.service != old_bed.room.service:
                return JsonResponse(
                    {"success": False, "error": "Le lit doit être dans le même service"}
                )

            # Récupérer le personnel connecté
            try:
                transferred_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                transferred_by = None

            # Date/heure du transfert
            transfer_time = timezone.now()

            # 1. Finaliser le séjour actuel
            current_admission.bed_end_date = transfer_time
            current_admission.is_current_bed = False
            current_admission.bed_stay_cost = (
                current_admission.calculate_bed_stay_cost()
            )
            current_admission.save()

            # 2. Créer l'historique de séjour pour la traçabilité
            StayHistory.objects.create(
                patient=current_admission.patient,
                admission=main_admission,
                bed=current_admission.bed,
                start_date=current_admission.bed_start_date,
                end_date=transfer_time,
                cost=current_admission.bed_stay_cost,
                notes=f"Séjour dans chambre {old_bed.room.room_number}, lit {old_bed.bed_number}",
            )

            # 3. CORRECTION: Créer une nouvelle entrée d'admission pour le nouveau lit
            # SANS référencer l'admission_request pour éviter la contrainte d'unicité
            new_bed_admission = Admission.objects.create(
                patient=patient,
                bed=new_bed,
                parent_admission=main_admission,
                admission_request=None,  # CORRECTION: Ne pas dupliquer la référence
                attending_doctor=current_admission.attending_doctor,
                admission_date=main_admission.admission_date,
                bed_start_date=transfer_time,
                diagnosis=current_admission.diagnosis,
                treatment_plan=current_admission.treatment_plan,
                is_current_bed=True,
                created_by=transferred_by,
            )

            # 4. Créer l'historique du transfert
            TransferHistory.objects.create(
                admission=main_admission,
                from_bed=current_admission.bed,
                to_bed=new_bed,
                transferred_by=transferred_by,
                reason=reason,
                transfer_date=transfer_time,
            )

            # 5. Mettre à jour les lits
            old_bed.is_occupied = False
            old_bed.save()

            new_bed.is_occupied = True
            new_bed.save()

            # 6. Calculer le coût cumulé jusqu'à présent
            total_cost_so_far = sum(
                stay.bed_stay_cost or 0
                for stay in main_admission.get_all_bed_stays()
                if stay.bed_stay_cost
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": "Patient transféré avec succès",
                    "patient_name": f"{patient.last_name} {patient.first_name}",
                    "old_bed": f"Chambre {old_bed.room.room_number} - Lit {old_bed.bed_number}",
                    "new_bed": f"Chambre {new_bed.room.room_number} - Lit {new_bed.bed_number}",
                    "old_bed_stay_cost": float(current_admission.bed_stay_cost),
                    "total_cost_so_far": float(total_cost_so_far),
                    "new_admission_id": new_bed_admission.id,
                }
            )

    except Exception as e:
        import traceback

        print(f"Erreur transfert: {traceback.format_exc()}")
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def admission_detail_api(request, admission_id):
    """API pour récupérer les détails d'une admission"""
    try:
        admission = get_object_or_404(
            Admission.objects.select_related(
                "patient", "bed__room__service", "attending_doctor__personnel__user"
            ),
            id=admission_id,
        )

        # Calculer la durée de séjour
        length_of_stay = admission.length_of_stay

        # Calculer le coût estimé
        estimated_cost = float(admission.calculate_total_cost())

        response_data = {
            "success": True,
            "admission": {
                "id": admission.id,
                "admission_date": admission.admission_date.isoformat(),
                "discharge_date": (
                    admission.discharge_date.isoformat()
                    if admission.discharge_date
                    else None
                ),
                "length_of_stay": length_of_stay,
                "diagnosis": admission.diagnosis or "",
                "treatment_plan": admission.treatment_plan or "",
                "estimated_cost": estimated_cost,
                "patient": {
                    "id": admission.patient.id,
                    "last_name": admission.patient.last_name,
                    "first_name": admission.patient.first_name,
                    "social_security_number": getattr(
                        admission.patient, "social_security_number", ""
                    )
                    or "",
                    "date_of_birth": (
                        admission.patient.date_of_birth.isoformat()
                        if hasattr(admission.patient, "date_of_birth")
                        and admission.patient.date_of_birth
                        else None
                    ),
                },
                "bed": {
                    "id": admission.bed.id,
                    "bed_number": admission.bed.bed_number,
                    "room": {
                        "id": admission.bed.room.id,
                        "room_number": admission.bed.room.room_number,
                        "service": admission.bed.room.service.name,
                        "night_price": float(admission.bed.room.night_price),
                    },
                },
                "attending_doctor": (
                    {
                        "id": admission.attending_doctor.id,
                        "nom_complet": admission.attending_doctor.nom_complet,
                    }
                    if admission.attending_doctor
                    else None
                ),
            },
        }

        return JsonResponse(response_data)

    except Admission.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Admission non trouvée"}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def discharge_patient(request, admission_id):
    """Vue pour la sortie d'un patient - Version robuste"""
    try:
        admission = get_object_or_404(Admission, id=admission_id, is_active=True)
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Admission non trouvée: {str(e)}"}, status=404
        )

    if request.method == "POST":
        try:
            # Récupérer les données du formulaire
            discharge_destination = request.POST.get(
                "discharge_destination", ""
            ).strip()
            discharge_notes = request.POST.get("discharge_notes", "").strip()

            # Validation des données
            if not discharge_destination:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "La destination de sortie est obligatoire",
                    },
                    status=400,
                )

            if not discharge_notes:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Les notes de sortie sont obligatoires",
                    },
                    status=400,
                )

            # Vérifications de sécurité
            if admission.discharge_date is not None:
                return JsonResponse(
                    {"success": False, "error": "Ce patient a déjà été sorti"},
                    status=400,
                )

            with transaction.atomic():
                # Sauvegarder les références avant modification
                bed = admission.bed
                admission_request = admission.admission_request

                # Calculer le coût total avant la sauvegarde
                try:
                    calculated_cost = admission.calculate_total_cost()
                except Exception as cost_error:
                    # Si le calcul échoue, utiliser une valeur par défaut
                    calculated_cost = Decimal("0.00")
                    print(f"Erreur calcul coût: {cost_error}")

                # Mettre à jour l'admission avec une approche différente
                current_time = timezone.now()

                # Mise à jour directe en base pour éviter les problèmes de propriétés
                updated_rows = Admission.objects.filter(
                    id=admission.id, is_active=True, discharge_date__isnull=True
                ).update(
                    discharge_date=current_time,
                    discharge_notes=discharge_notes,
                    discharge_destination=discharge_destination,
                    is_active=False,
                    total_cost=calculated_cost,
                )

                if updated_rows == 0:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Impossible de mettre à jour l'admission - elle a peut-être déjà été modifiée",
                        },
                        status=400,
                    )

                # Libérer le lit
                if bed:
                    try:
                        bed.is_occupied = False
                        bed.last_cleaned = None
                        bed.save()
                    except Exception as bed_error:
                        print(f"Erreur mise à jour lit: {bed_error}")
                        # Ne pas faire échouer toute l'opération pour cela

                # Mettre à jour la demande d'admission si elle existe
                if admission_request:
                    try:
                        admission_request.status = (
                            "admitted"  # ou "completed" selon votre logique
                        )
                        admission_request.save()
                    except Exception as request_error:
                        print(f"Erreur mise à jour demande: {request_error}")

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Sortie enregistrée avec succès",
                        "admission_id": admission.id,
                        "total_cost": float(calculated_cost),
                    }
                )

        except Exception as e:
            # Log détaillé de l'erreur
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.error(
                f"Erreur lors de la sortie du patient {admission_id}: {str(e)}"
            )
            logger.error(f"Traceback: {traceback.format_exc()}")

            return JsonResponse(
                {
                    "success": False,
                    "error": f"Erreur lors de l'enregistrement de la sortie: {str(e)}",
                },
                status=500,
            )

    # Pour les requêtes GET - retourner les détails de l'admission
    try:
        context = {
            "admission": admission,
            "patient": admission.patient,
            "bed": admission.bed,
            "room": admission.bed.room if admission.bed else None,
        }
        return JsonResponse(
            {
                "success": True,
                "admission": {
                    "id": admission.id,
                    "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                    "room_number": (
                        admission.bed.room.room_number
                        if admission.bed and admission.bed.room
                        else "N/A"
                    ),
                    "bed_number": admission.bed.bed_number if admission.bed else "N/A",
                    "admission_date": admission.admission_date.strftime(
                        "%d/%m/%Y %H:%M"
                    ),
                    "length_of_stay": admission.length_of_stay,
                    "diagnosis": admission.diagnosis or "",
                    "treatment_plan": admission.treatment_plan or "",
                },
            }
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Erreur lors du chargement: {str(e)}"},
            status=500,
        )


@login_required
def update_bed_status(request, bed_id):
    """Mettre à jour le statut d'un lit (maintenance, etc.)"""
    if request.method == "POST":
        bed = get_object_or_404(Bed, id=bed_id)

        try:
            maintenance_required = request.POST.get("maintenance_required") == "on"
            bed.maintenance_required = maintenance_required

            if maintenance_required and bed.is_occupied:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Impossible de mettre un lit occupé en maintenance",
                    }
                )

            bed.save()

            return JsonResponse(
                {"success": True, "message": "Statut du lit mis à jour avec succès"}
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})


@login_required
def room_detail_api(request, room_id):
    """API pour récupérer les détails d'une chambre"""
    try:
        room = get_object_or_404(
            Room.objects.prefetch_related("beds__admissions__patient"), id=room_id
        )

        # Préparer les données des lits
        beds_data = []
        for bed in room.beds.all():
            current_patient = None
            if bed.is_occupied and bed.current_patient:
                current_patient = (
                    f"{bed.current_patient.last_name} {bed.current_patient.first_name}"
                )

            beds_data.append(
                {
                    "id": bed.id,
                    "bed_number": bed.bed_number,
                    "is_occupied": bed.is_occupied,
                    "maintenance_required": bed.maintenance_required,
                    "current_patient": current_patient,
                    "bed_type": bed.get_bed_type_display(),
                }
            )

        response_data = {
            "success": True,
            "room": {
                "id": room.id,
                "room_number": room.room_number,
                "floor": room.floor,
                "room_type": room.room_type,
                "room_type_display": room.get_room_type_display(),
                "bed_capacity": room.bed_capacity,
                "night_price": float(room.night_price),
                "is_active": room.is_active,
                "maintenance_required": room.maintenance_required,
                "room_equipment": room.room_equipment or "",
                "special_requirements": room.special_requirements or "",
                "occupied_beds_count": room.occupied_beds_count,
                "available_beds_count": room.available_beds_count,
                "occupancy_rate": room.occupancy_rate,
                "beds": beds_data,
            },
        }

        return JsonResponse(response_data)

    except Room.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Chambre non trouvée"}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@csrf_exempt
def cancel_admission_request(request, request_id):
    """API pour annuler une demande d'admission"""
    if request.method == "POST":
        try:
            admission_request = get_object_or_404(AdmissionRequest, id=request_id)

            if admission_request.status != "waiting":
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Seules les demandes en attente peuvent être annulées",
                    }
                )

            admission_request.status = "cancelled"
            admission_request.save()

            return JsonResponse(
                {"success": True, "message": "Demande d'admission annulée avec succès"}
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})
