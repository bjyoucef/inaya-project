from django.urls import path

from . import views
from .views.audits import audit_detail, audit_list, audit_prestation_detail
from .views.bloc_location import (
    ActeDetailView,
    ForfaitDetailView,
    LocationBlocCreateView,
    LocationBlocDeleteView,
    LocationBlocDetailView,  # Vue unifiée
    LocationBlocEditView,
    LocationBlocListView,
    get_acte_produits,
    get_all_actes_data,
    get_all_blocs_data,
    get_all_forfaits_data,
    get_bloc_produits,
    get_forfait_produits,
    get_produits_supplementaires,
    LocationBlocExportPDFView,
    locations_en_attente_reglement,
    marquer_reglement_complement,
    marquer_reglement_surplus,
    modifier_paiement_location,
    send_location_invoice_whatsapp,
)
from .views.prestations_kt import (GetActeProduitsView, GetTarifView,
                                   PatientPrestationHistoryView,
                                   PrestationCreateView, PrestationDeleteView,
                                   PrestationDetailView, PrestationListView,
                                   PrestationProgrammerView,
                                   PrestationUpdateView)

app_name = "medical"

urlaudit = [
    path("audit/", audit_list, name="audit_list"),
    path(
        "audit/prestation/<int:prestation_id>/",
        audit_prestation_detail,
        name="audit_prestation_detail",
    ),
    path("audit/detail/<int:audit_id>/", audit_detail, name="audit_detail"),
]

urlpatterns = [
    # Prestations
    path(
        "programmer/",
        PrestationProgrammerView.as_view(),
        name="prestation_programmer",
    ),
    path(
        "prestations/create/", PrestationCreateView.as_view(), name="prestation_create"
    ),
    path("prestations/", PrestationListView.as_view(), name="prestation_list"),
    path(
        "prestations/<int:prestation_id>/",
        PrestationDetailView.as_view(),
        name="prestation_detail",
    ),
    path(
        "prestations/<int:prestation_id>/update/",
        PrestationUpdateView.as_view(),
        name="prestation_update",
    ),
    path(
        "prestations/<int:prestation_id>/delete/",
        PrestationDeleteView.as_view(),
        name="prestation_delete",
    ),
    path("get-tarif/", GetTarifView.as_view(), name="get_tarif"),
    path(
        "get-acte-produits/<int:acte_id>/",
        GetActeProduitsView.as_view(),
        name="get_acte_produits",
    ),
    path(
        "prestations/history/<int:patient_id>/",
        PatientPrestationHistoryView.as_view(),
        name="patient_prestation_history",
    ),
    # Locations de bloc
    path("locations-bloc/", LocationBlocListView.as_view(), name="location_bloc_list"),
    path(
        "locations-bloc/create/",
        LocationBlocCreateView.as_view(),
        name="location_bloc_create",
    ),
    # Vue unifiée - Point d'entrée principal
    path(
        "locations-bloc/<int:location_id>/",
        LocationBlocDetailView.as_view(),
        name="location_bloc_detail",
    ),
    # Maintenir pour compatibilité - redirige vers la vue unifiée
    path(
        "locations-bloc/<int:location_id>/edit/",
        LocationBlocEditView.as_view(),
        name="location_bloc_edit",
    ),
    path(
        "locations-bloc/<int:location_id>/delete/",
        LocationBlocDeleteView.as_view(),
        name="location_bloc_delete",
    ),
    # Export et partage
    path(
        "locations-bloc/<int:location_id>/export/pdf/",
        LocationBlocExportPDFView.as_view(),
        name="location_bloc_export_pdf",
    ),
    path(
        "locations-bloc/<int:location_id>/send-whatsapp/",
        send_location_invoice_whatsapp,
        name="location_bloc_send_whatsapp",
    ),
    # APIs
    path(
        "api/forfait/<int:forfait_id>/",
        ForfaitDetailView.as_view(),
        name="api_forfait_detail",
    ),
    path(
        "api/acte/<int:acte_id>/",
        ActeDetailView.as_view(),
        name="api_acte_detail",
    ),
    # AJAX endpoints pour le chargement des données
    path("ajax/blocs-data/", get_all_blocs_data, name="ajax_get_all_blocs_data"),
    path(
        "ajax/forfaits-data/", get_all_forfaits_data, name="ajax_get_all_forfaits_data"
    ),
    path("ajax/actes-data/", get_all_actes_data, name="ajax_get_all_actes_data"),
    path(
        "ajax/produits-supplementaires/",
        get_produits_supplementaires,
        name="ajax_get_produits_supplementaires",
    ),
    # AJAX endpoints spécifiques (pour compatibilité et usage ciblé)
    path(
        "ajax/bloc/<int:bloc_id>/produits/",
        get_bloc_produits,
        name="ajax_get_bloc_produits",
    ),
    path(
        "ajax/forfait/<int:forfait_id>/produits/",
        get_forfait_produits,
        name="ajax_get_forfait_produits",
    ),
    path(
        "ajax/acte/<int:acte_id>/produits/",
        get_acte_produits,
        name="ajax_get_acte_produits",
    ),
    # Nouvelles URLs pour la gestion des paiements
    path(
        "locations/<int:location_id>/marquer-reglement-surplus/",
        marquer_reglement_surplus,
        name="marquer_reglement_surplus",
    ),
    path(
        "locations/<int:location_id>/marquer-reglement-complement/",
        marquer_reglement_complement,
        name="marquer_reglement_complement",
    ),
    path(
        "locations/<int:location_id>/modifier-paiement/",
        modifier_paiement_location,
        name="modifier_paiement_location",
    ),
    path(
        "locations/reglements-en-attente/",
        locations_en_attente_reglement,
        name="locations_reglements_en_attente",
    ),
] + urlaudit
