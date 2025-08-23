# urls.py
from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    # CRUD principal
    path("", views.patient_list, name="patient_list"),
    path("create/", views.patient_create, name="patient_create"),
    path("<int:patient_id>/", views.patient_detail, name="patient_detail"),
    path("<int:patient_id>/update/", views.patient_update, name="patient_update"),
    path("<int:patient_id>/delete/", views.patient_delete, name="patient_delete"),
    path(
        "<int:patient_id>/toggle-status/",
        views.patient_toggle_status,
        name="patient_toggle_status",
    ),
    # API
    path("api/search/", views.patient_search_api, name="patient_search_api"),
]
