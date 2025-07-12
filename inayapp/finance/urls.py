from django.urls import path
from . import views


urlpatterns = [
    path(
        "add-decharge-multiple/",
        views.add_decharge_multiple,
        name="add_decharge_multiple",
    ),
    path(
        "situation-medecin/<int:medecin_id>/create-decharge/",
        views.create_decharge_medecin,
        name="create_decharge",
    ),
    path("decharge/", views.decharge_list, name="decharge_list"),
    path("decharge/reglees/", views.decharge_settled, name="decharge_settled"),
    path("decharge/create/", views.decharge_create, name="decharge_create"),
    path("decharge/<int:pk>/", views.decharge_detail, name="decharge_detail"),
    path("decharge/<int:pk>/edit/", views.decharge_edit, name="decharge_edit"),
    path("decharge/<int:pk>/delete/", views.decharge_delete, name="decharge_delete"),
    path(
        "decharge/payment/<int:pk>/delete/", views.payment_delete, name="payment_delete"
    ),
    path(
        "decharges/<int:decharge_id>/export/",
        views.export_decharge_pdf,
        name="export_decharge_pdf",
    ),
    path(
        "decharges/<int:decharge_id>/print/",
        views.print_decharge_view,
        name="print_decharge",
    ),
    path(
        "situation-medecin/",
        views.situation_medecins_list,
        name="situation_medecins_list",
    ),
    path(
        "situation-medecin/<int:medecin_id>/",
        views.situation_medecin,
        name="situation_medecin",
    ),
    path(
        "conventions-status/",
        views.gestion_convention_accorde,
        name="gestion_convention_accorde",
    ),
    path(
        "conventions-status/<int:pk>/update/",
        views.update_convention_status,
        name="update_convention_status",
    ),
    path("paiements/especes/", views.paiements_especes, name="paiements_especes"),
    path(
        "paiements/bon/<int:prestation_id>/",
        views.creer_bon_paiement,
        name="creer_bon_paiement",
    ),
]
