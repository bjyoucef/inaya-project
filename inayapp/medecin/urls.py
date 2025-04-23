from django.urls import path
from . import views

app_name = "medecins"

urlpatterns = [
    path("", views.MedecinListView.as_view(), name="list"),
    path("ajouter/", views.MedecinCreateView.as_view(), name="add"),
    path("<int:pk>/modifier/", views.MedecinUpdateView.as_view(), name="edit"),
    path("<int:pk>/supprimer/", views.MedecinDeleteView.as_view(), name="delete"),
]
