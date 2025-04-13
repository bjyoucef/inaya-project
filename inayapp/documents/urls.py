from django.urls import path
from . import views

urlpatterns = [
    path('', views.liste_documents, name='liste_documents'),
]
