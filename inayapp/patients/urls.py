from django.urls import path
from .views import (
    PatientListView,
    PatientCreateView,
    PatientUpdateView,
    PatientDeleteView,
)

urlpatterns = [
    path("", PatientListView.as_view(), name="patient_list"),
    path("patients/new/", PatientCreateView.as_view(), name="patient_create"),
    path("patients/<int:pk>/edit/", PatientUpdateView.as_view(), name="patient_update"),
    path(
        "patients/<int:pk>/delete/", PatientDeleteView.as_view(), name="patient_delete"
    ),
]
