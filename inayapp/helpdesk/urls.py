from django.urls import path
from . import views

urlpatterns = [
    path("helpdesk/", views.demande_assistance, name="demande_assistance"),
    path("envoyer_demandeIt/", views.envoyer_demandeIt, name="envoyer_demandeIt"),
    path("envoyer_demandeTech/", views.envoyer_demandeTech, name="envoyer_demandeTech"),
    path(
        "envoyer_demandeAppro/", views.envoyer_demandeAppro, name="envoyer_demandeAppro"
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("mark_terminee/<int:demande_id>/", views.mark_terminee, name="mark_terminee"),
    # APIs
    path(
        "api/demande/<int:demande_id>/",
        views.get_demande_details,
        name="get_demande_details",
    ),
    path(
        "api/demande/<int:demande_id>/status/",
        views.update_demande_status,
        name="update_demande_status",
    ),
    # Fichiers et médias
    path("download/<path:filename>/", views.download_file, name="download_file"),
    path("audio/<path:audio_path>/", views.serve_audio, name="serve_audio"),
]
