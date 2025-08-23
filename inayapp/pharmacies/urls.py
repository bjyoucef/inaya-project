# pharmacies/urls.py
from django.urls import include, path

from . import views
from .views.approvisionnement import (  # Nouvelles vues pour demandes internes
    BonReceptionDetailView, BonReceptionListView, BonReceptionPrintView,
    CommandeFournisseurConfirmView, CommandeFournisseurCreateView,
    CommandeFournisseurDetailView, CommandeFournisseurListView, DashboardView,
    ExpressionBesoinCreateView, ExpressionBesoinDetailView,
    ExpressionBesoinListView, ExpressionBesoinValidationView,
    GetBesoinLignesAPIView, GetCommandeLignesAPIView, GetProduitsAPIView,
    GetStockDisponibleAPIView, GetStocksMultiplesAPIView, LivraisonCreateView,
    LivraisonDetailView, LivraisonListView, LivraisonReceptionView,
    menu_stats_api, system_alerts_api)
from .views.views_fournisseur import (FournisseurCreateView,
                                      FournisseurDeleteView,
                                      FournisseurDetailView,
                                      FournisseurListView,
                                      FournisseurUpdateView)
from .views.views_stock import (AjustementStockCreateView, StockCreateView,
                                StockDeleteView, StockDetailView,
                                StockListView, StockUpdateView,
                                get_stock_disponible, stocks_expires_bientot)
from .views import approvisionnement_interne

app_name = "pharmacies"

urls_interne = [
    # Liste et gestion des demandes internes
    path(
        "approvisionnement/demandes-internes/",
        approvisionnement_interne.liste_demandes_internes,
        name="liste_demandes_internes",
    ),
    path(
        "approvisionnement/demandes-internes/nouvelle/",
        approvisionnement_interne.nouvelle_demande_interne,
        name="nouvelle_demande_interne",
    ),
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/",
        approvisionnement_interne.detail_demande_interne,
        name="detail_demande_interne",
    ),
    # Actions sur les demandes
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/valider/",
        approvisionnement_interne.valider_demande_interne,
        name="valider_demande_interne",
    ),
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/rejeter/",
        approvisionnement_interne.rejeter_demande_interne,
        name="rejeter_demande_interne",
    ),
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/preparer/",
        approvisionnement_interne.preparer_demande_interne,
        name="preparer_demande_interne",
    ),
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/livrer/",
        approvisionnement_interne.livrer_demande_interne,
        name="livrer_demande_interne",
    ),
    path(
        "approvisionnement/demandes-internes/<int:demande_id>/annuler/",
        approvisionnement_interne.annuler_demande_interne,
        name="annuler_demande_interne",
    ),
    # APIs
    path(
        "approvisionnement/api/stock-disponible/",
        approvisionnement_interne.api_stock_disponible,
        name="api_stock_disponible",
    ),
    path(
        "approvisionnement/api/recherche-produits/",
        approvisionnement_interne.api_recherche_produits,
        name="api_recherche_produits",
    ),
    # Rapports
    path(
        "approvisionnement/rapports/demandes-internes/",
        approvisionnement_interne.rapport_demandes_internes,
        name="rapport_demandes_internes",
    ),
]

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
    path("approvisionnement/api/stats-menu/", menu_stats_api, name="api_stats_menu"),
] + urls_interne
