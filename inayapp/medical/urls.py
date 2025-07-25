from django.urls import path

from . import views
from .views import GetActeProduitsView

app_name = "medical"

urlaudit = [
    path("audit", views.audit_list, name="audit_list"),
    path(
        "audit/prestation/<int:prestation_id>/",
        views.audit_prestation_detail,
        name="audit_prestation_detail",
    ),
    path("audit/detail/<int:audit_id>/", views.audit_detail, name="audit_detail"),
]

urlpatterns = [
    path(
        "programmer/",
        views.PrestationProgrammerView.as_view(),
        name="prestation_programmer",
    ),
    path(
        "prestations/nouveau/",
        views.PrestationCreateView.as_view(),
        name="prestation_create",
    ),
    path("prestations/", views.PrestationListView.as_view(), name="prestation_list"),
    path(
        "prestations/<int:prestation_id>/",
        views.PrestationDetailView.as_view(),
        name="prestation_detail",
    ),
    path(
        "prestations/<int:prestation_id>/",
        views.PrestationDetailView.as_view(),
        name="prestation_detail",
    ),
    path(
        "prestations/<int:prestation_id>/edit/",
        views.PrestationUpdateView.as_view(),
        name="prestation_update",
    ),
    path(
        "prestations/<int:prestation_id>/delete/",
        views.PrestationDeleteView.as_view(),
        name="prestation_delete",
    ),
    path("get-tarif/", views.GetTarifView.as_view(), name="get_tarif"),
    path(
        "get-acte-produits/<int:acte_id>/",
        GetActeProduitsView.as_view(),
        name="get_acte_produits",
    ),
    path(
        "prestations/history/<int:patient_id>/",
        views.PatientPrestationHistoryView.as_view(),
        name="patient_prestation_history",
    ),
] + urlaudit
