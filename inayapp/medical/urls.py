from django.urls import path
from . import views

app_name = "medical"  # ou le nom de votre app

urlpatterns = [
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
]
