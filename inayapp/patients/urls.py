from django.urls import path
from .views import (
    PatientListView,
    PatientCreateView,
    PatientUpdateView,
    PatientDeleteView,
)

app_name = "patients"

urlpatterns = [
    path("", PatientListView.as_view(), name="list"),
    path("ajouter/", PatientCreateView.as_view(), name="add"),
    path("<int:pk>/modifier/", PatientUpdateView.as_view(), name="edit"),
    path("<int:pk>/supprimer/", PatientDeleteView.as_view(), name="delete"),
]
