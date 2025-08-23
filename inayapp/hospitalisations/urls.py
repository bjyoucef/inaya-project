# hospitalisation/urls.py
from django.urls import path
from . import views

app_name = "hospitalisation"

urlpatterns = [
    # Plan d'étage centralisé
    path(
        "service/<int:service_id>/plan/",
        views.floor_plan_centralized,
        name="floor_plan_centralized",
    ),
    # Gestion des demandes d'admission
    path(
        "api/add-admission-request/",
        views.add_admission_request,
        name="add_admission_request",
    ),

    path(
        "api/cancel-request/<int:request_id>/",
        views.cancel_admission_request,
        name="cancel_admission_request",
    ),
    # API pour les opérations principales
    path("api/admit-patient/", views.admit_patient, name="admit_patient"),
    path("api/transfer-patient/", views.transfer_patient, name="transfer_patient"),
    # API pour les détails des admissions
    path(
        "api/admission/<int:admission_id>/",
        views.admission_detail_api,
        name="admission_detail_api",
    ),
    # Gestion des patients
    path(
        "admissions/<int:admission_id>/sortie/",
        views.discharge_patient,
        name="discharge_patient",
    ),
    # Gestion des chambres

    path(
        "api/room/<int:room_id>/",
        views.room_detail_api,
        name="room_detail_api",
    ),


    # Mise à jour du statut des lits
    path(
        "api/bed/<int:bed_id>/update-status/",
        views.update_bed_status,
        name="update_bed_status",
    ),
]
