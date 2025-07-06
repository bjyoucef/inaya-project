# audit/urls.py
from django.urls import path
from . import views

app_name = "audit"

urlpatterns = [
    path("dashboard/", views.audit_dashboard, name="dashboard"),
    path("api/stats/", views.audit_api_stats, name="api_stats"),
]
