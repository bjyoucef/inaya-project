from django.urls import path
from . import views


urlpatterns = [
    path(
        "add-decharge-multiple/",
        views.add_decharge_multiple,
        name="add_decharge_multiple",
    ),
    path(
        "decharges_payments/",
        views.manage_decharges_payments,
        name="manage_decharges_payments",
    ),
]
