from django.urls import path
from . import views


urlpatterns = [
    path(
        "add-decharge-multiple/",
        views.add_decharge_multiple,
        name="add_decharge_multiple",
    ),
    path(
        "medecin/<int:medecin_id>/create-decharge/",
        views.create_decharge_medecin,
        name="create_decharge",
    ),
    path("", views.decharge_list, name="decharge_list"),
    path("reglees/", views.decharge_settled, name="decharge_settled"),
    path("create/", views.decharge_create, name="decharge_create"),
    path("<int:pk>/", views.decharge_detail, name="decharge_detail"),
    path("<int:pk>/edit/", views.decharge_edit, name="decharge_edit"),
    path("<int:pk>/delete/", views.decharge_delete, name="decharge_delete"),
    path("payment/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
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
        "situation-medecin-list/",
        views.situation_medecins_list,
        name="situation_medecins_list",
    ),
    path(
        "situation-medecin/<int:medecin_id>/",
        views.situation_medecin,
        name="situation_medecin",
    ),
]
