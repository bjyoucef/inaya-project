# pharmacies/urls.py
from django.urls import include, path

from . import views

from .views.views_fournisseur import (
    FournisseurCreateView,
    FournisseurDeleteView,
    FournisseurDetailView,
    FournisseurListView,
    FournisseurUpdateView,
)
from .views.views_stock import (
    AjustementStockCreateView,
    StockCreateView,
    StockDeleteView,
    StockDetailView,
    StockListView,
    StockUpdateView,
    get_stock_disponible,
    stocks_expires_bientot,
)
from django.urls import path
from .views.approvisionnement import (
    ExpressionBesoinListView,
    ExpressionBesoinDetailView,
    ExpressionBesoinCreateView,
    ExpressionBesoinValidationView,
    CommandeFournisseurListView,
    CommandeFournisseurDetailView,
    CommandeFournisseurCreateView,
    CommandeFournisseurConfirmView,
    LivraisonListView,
    LivraisonDetailView,
    LivraisonCreateView,
    LivraisonReceptionView,
    BonReceptionListView,
    BonReceptionDetailView,
    BonReceptionPrintView,
    GetBesoinLignesAPIView,
    GetCommandeLignesAPIView,
    GetProduitsAPIView,
    DashboardView,
    # Nouvelles vues pour demandes internes
    DemandeInterneListView,
    DemandeInterneDetailView,
    DemandeInterneValidationView,
    DemandeInterneValiderView,
    DemandeInterneRejeterView,
    DemandeInternePreparerView,
    DemandeInterneLivrerView,
    DemandeInternePDFView,
    DemandeInterneExcelView,
    GetStockDisponibleAPIView,
    GetStocksMultiplesAPIView,
    system_alerts_api,
    menu_stats_api,
)


app_name = "pharmacies"
urlpatterns = [
    # Produits
    path("produits/", views.ProduitListView.as_view(), name="produit_list"),
    path("produits/create/", views.ProduitCreateView.as_view(), name="produit_create"),
    path(
        "produits/<int:pk>/", views.ProduitDetailView.as_view(), name="produit_detail"
    ),
    path(
        "produits/<int:pk>/edit/",
        views.ProduitUpdateView.as_view(),
        name="produit_update",
    ),
    path(
        "produits/<int:pk>/delete/",
        views.ProduitDeleteView.as_view(),
        name="produit_delete",
    ),
    # Stocks
    path("stocks/", StockListView.as_view(), name="stock_list"),
    path("stocks/ajouter/", StockCreateView.as_view(), name="stock_create"),
    path("stocks/<int:pk>/", StockDetailView.as_view(), name="stock_detail"),
    path("stocks/<int:pk>/modifier/", StockUpdateView.as_view(), name="stock_update"),
    path("stocks/<int:pk>/supprimer/", StockDeleteView.as_view(), name="stock_delete"),
    # Ajustements
    path(
        "ajustements/nouveau/",
        AjustementStockCreateView.as_view(),
        name="ajustement_create",
    ),
    # API
    path("api/stock-disponible/", get_stock_disponible, name="stock_disponible"),
    path("api/stocks-expires/", stocks_expires_bientot, name="stocks_expires"),
    # Fournisseur
    path("fournisseurs/", FournisseurListView.as_view(), name="liste"),
    path("fournisseurs/ajouter/", FournisseurCreateView.as_view(), name="creer"),
    path("fournisseurs/<int:pk>/", FournisseurDetailView.as_view(), name="detail"),
    path(
        "fournisseurs/<int:pk>/modifier/",
        FournisseurUpdateView.as_view(),
        name="modifier",
    ),
    path(
        "fournisseurs/<int:pk>/supprimer/",
        FournisseurDeleteView.as_view(),
        name="supprimer",
    ),
] + [
    # Approvisionnement******************************
    # Dashboard
    path(
        "approvisionnement/dashboard/",
        DashboardView.as_view(),
        name="approvisionnement_dashboard",
    ),
    # Expression de besoin
    path(
        "approvisionnement/besoins/",
        ExpressionBesoinListView.as_view(),
        name="expression_besoin_list",
    ),
    path(
        "approvisionnement/besoins/<int:pk>/",
        ExpressionBesoinDetailView.as_view(),
        name="expression_besoin_detail",
    ),
    path(
        "approvisionnement/besoins/nouveau/",
        ExpressionBesoinCreateView.as_view(),
        name="expression_besoin_create",
    ),
    # Dans pharmacies/urls.py
    path(
        "approvisionnement/besoins/<int:pk>/validation/",
        ExpressionBesoinValidationView.as_view(),
        name="expression_besoin_validation",
    ),
    # Demandes internes
    path(
        "demandes-internes/",
        DemandeInterneListView.as_view(),
        name="demande_interne_list",
    ),
    path(
        "demandes-internes/<int:pk>/",
        DemandeInterneDetailView.as_view(),
        name="demande_interne_detail",
    ),
    path(
        "demandes-internes/<int:pk>/validation/",
        DemandeInterneValidationView.as_view(),
        name="demande_interne_validation",
    ),
    # Actions sur les demandes internes - AJOUT DE CES URLs MANQUANTES
    path(
        "demandes-internes/<int:pk>/valider/",
        DemandeInterneValiderView.as_view(),
        name="demande_interne_valider",
    ),
    path(
        "demandes-internes/<int:pk>/rejeter/",
        DemandeInterneRejeterView.as_view(),
        name="demande_interne_rejeter",
    ),
    path(
        "demandes-internes/<int:pk>/preparer/",
        DemandeInternePreparerView.as_view(),
        name="demande_interne_preparer",
    ),
    path(
        "demandes-internes/<int:pk>/livrer/",
        DemandeInterneLivrerView.as_view(),
        name="demande_interne_livrer",
    ),
    # Export des demandes internes
    path(
        "demandes-internes/<int:pk>/pdf/",
        DemandeInternePDFView.as_view(),
        name="demande_interne_pdf",
    ),
    path(
        "demandes-internes/<int:pk>/excel/",
        DemandeInterneExcelView.as_view(),
        name="demande_interne_excel",
    ),
    # Commandes fournisseurs (approvisionnement externe)
    path(
        "commandes/",
        CommandeFournisseurListView.as_view(),
        name="commande_fournisseur_list",
    ),
    path(
        "approvisionnement/commandes/<int:pk>/",
        CommandeFournisseurDetailView.as_view(),
        name="commande_fournisseur_detail",
    ),
    path(
        "approvisionnement/commandes/nouveau/",
        CommandeFournisseurCreateView.as_view(),
        name="commande_fournisseur_create",
    ),
    path(
        "approvisionnement/commandes/<int:pk>/confirmer/",
        CommandeFournisseurConfirmView.as_view(),
        name="commande_fournisseur_confirm",
    ),
    # Livraison
    path(
        "approvisionnement/livraisons/",
        LivraisonListView.as_view(),
        name="livraison_list",
    ),
    path(
        "approvisionnement/livraisons/<int:pk>/",
        LivraisonDetailView.as_view(),
        name="livraison_detail",
    ),
    path(
        "approvisionnement/livraisons/nouveau/",
        LivraisonCreateView.as_view(),
        name="livraison_create",
    ),
    path(
        "approvisionnement/livraisons/<int:pk>/reception/",
        LivraisonReceptionView.as_view(),
        name="livraison_reception",
    ),
    # Bon de réception
    path(
        "approvisionnement/bons-reception/",
        BonReceptionListView.as_view(),
        name="bon_reception_list",
    ),
    path(
        "approvisionnement/bons-reception/<int:pk>/",
        BonReceptionDetailView.as_view(),
        name="bon_reception_detail",
    ),
    path(
        "approvisionnement/bons-reception/<int:pk>/imprimer/",
        BonReceptionPrintView.as_view(),
        name="bon_reception_print",
    ),
    # API
    path(
        "approvisionnement/api/besoins/<int:pk>/lignes/",
        GetBesoinLignesAPIView.as_view(),
        name="api_besoin_lignes",
    ),
    path(
        "approvisionnement/api/commandes/<int:pk>/lignes/",
        GetCommandeLignesAPIView.as_view(),
        name="api_commande_lignes",
    ),
    path(
        "approvisionnement/api/produits/",
        GetProduitsAPIView.as_view(),
        name="api_produits",
    ),
    path(
        "api/stock-disponible/<int:produit_id>/",
        GetStockDisponibleAPIView.as_view(),
        name="api_stock_disponible",
    ),
    path(
        "api/stocks-multiples/",
        GetStocksMultiplesAPIView.as_view(),
        name="api_stocks_multiples",
    ),
    path(
        "approvisionnement/api/alertes-systeme/",
        system_alerts_api,
        name="api_alertes_systeme",
    ),
    path(
        "approvisionnement/api/stats-menu/", menu_stats_api, name="api_stats_menu"
    ),
]
