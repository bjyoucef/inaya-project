# inventaire/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"salles", views.SalleViewSet)
router.register(r"items", views.ItemViewSet)
router.register(r"stocks", views.StockViewSet)
router.register(r"mouvements", views.MouvementStockViewSet)
router.register(r"transferts", views.DemandeTransfertViewSet)
router.register(r"inventaires", views.InventaireViewSet)

app_name = "inventaire"

urlpatterns = [
    # API URLs
    path("api/", include(router.urls)),
    # Dashboard
    path("dashboard", views.DashboardView.as_view(), name="dashboard"),
    # Stock URLs
    path("stocks/", views.StockListView.as_view(), name="stock_list"),
    path("stocks/alerts/", views.StockAlertsView.as_view(), name="stock_alerts"),
    path("stocks/<int:pk>/", views.StockDetailView.as_view(), name="stock_detail"),
    # Mouvement URLs
    path("mouvements/", views.MouvementListView.as_view(), name="mouvement_list"),
    path(
        "mouvements/create/",
        views.MouvementCreateView.as_view(),
        name="mouvement_create",
    ),
    # Transfert URLs
    path("transferts/", views.TransfertListView.as_view(), name="transfert_list"),
    path(
        "transferts/create/",
        views.TransfertCreateView.as_view(),
        name="transfert_create",
    ),
    path(
        "transferts/<int:pk>/approve/",
        views.TransfertApproveView.as_view(),
        name="transfert_approve",
    ),
    # Inventaire URLs
    path("inventaires/", views.InventaireListView.as_view(), name="inventaire_list"),
    path(
        "inventaires/create/",
        views.InventaireCreateView.as_view(),
        name="inventaire_create",
    ),
    path(
        "inventaires/<int:pk>/",
        views.InventaireDetailView.as_view(),
        name="inventaire_detail",
    ),
    # Reports
    path("reports/stock/", views.StockReportView.as_view(), name="stock_report"),
    path(
        "reports/movements/", views.MovementReportView.as_view(), name="movement_report"
    ),
    # Barcode
    path("barcode/scan/", views.BarcodeScanView.as_view(), name="barcode_scan"),
    path(
        "barcode/generate/<int:item_id>/",
        views.BarcodeGenerateView.as_view(),
        name="barcode_generate",
    ),
    # Maintenance URLs
    path("maintenances/", views.MaintenanceListView.as_view(), name="maintenance_list"),
    path(
        "maintenances/create/",
        views.MaintenanceCreateView.as_view(),
        name="maintenance_create",
    ),
    path(
        "maintenances/<int:pk>/",
        views.MaintenanceDetailView.as_view(),
        name="maintenance_detail",
    ),
    path(
        "maintenances/<int:pk>/update/",
        views.MaintenanceUpdateView.as_view(),
        name="maintenance_update",
    ),
    # Mouvement Detail
    path(
        "mouvements/<int:pk>/",
        views.MouvementStockDetailView.as_view(),
        name="mouvement_detail",
    ),
    # Transfert Detail
    path(
        "transferts/<int:pk>/",
        views.TransfertDetailView.as_view(),
        name="transfert_detail",
    ),
]
