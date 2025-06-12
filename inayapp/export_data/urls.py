from django.urls import path
from . import views

app_name = "export_data"

urlpatterns = [
    path("", views.export_data_view, name="index"),
    path("preview/", views.get_model_preview, name="model_preview"),
    path("debug/", views.debug_apps, name="debug_apps"),
]
