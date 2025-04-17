from django.urls import path
from . import views


urlpatterns = [
    path(
        "add-decharge-multiple/",
        views.add_decharge_multiple,
        name="add_decharge_multiple",
    ),
    path("", views.decharge_list, name="decharge_list"),
    path("reglees/", views.decharge_settled, name="decharge_settled"),
    path("create/", views.decharge_create, name="decharge_create"),
    path("<int:pk>/", views.decharge_detail, name="decharge_detail"),
    path("<int:pk>/edit/", views.decharge_edit, name="decharge_edit"),
    path("<int:pk>/delete/", views.decharge_delete, name="decharge_delete"),
    path("payment/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
]
