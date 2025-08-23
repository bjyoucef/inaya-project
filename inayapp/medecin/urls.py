from django.urls import path
from . import views

urlpatterns = [
    # Liste et recherche
    path("", views.medecin_list, name="medecin_list"),
    # CRUD
    path("create/", views.medecin_create, name="medecin_create"),
    path("<int:pk>/", views.medecin_detail, name="medecin_detail"),
    path("<int:pk>/update/", views.medecin_update, name="medecin_update"),
    path("<int:pk>/delete/", views.medecin_delete, name="medecin_delete"),
    # AJAX
    path("ajax/search/", views.medecin_ajax_search, name="medecin_ajax_search"),
]
