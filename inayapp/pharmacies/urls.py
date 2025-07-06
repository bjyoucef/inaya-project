# pharmacies/urls.py
from django.urls import path

from .views.views_stock import AjustementStockCreateView,StockCreateView, StockDeleteView, StockDetailView, StockListView, StockUpdateView, get_stock_disponible, stocks_expires_bientot
from . import views
from django.urls import path
from .views.views_fournisseur import (
    FournisseurListView,
    FournisseurCreateView,
    FournisseurDetailView,
    FournisseurUpdateView,
    FournisseurDeleteView,
    OrdrePaiementCreateView,
    OrdrePaiementUpdateView,
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
    path('stocks/', StockListView.as_view(), name='stock_list'),
    path('stocks/ajouter/', StockCreateView.as_view(), name='stock_create'),
    path('stocks/<int:pk>/', StockDetailView.as_view(), name='stock_detail'),
    path('stocks/<int:pk>/modifier/', StockUpdateView.as_view(), name='stock_update'),
    path('stocks/<int:pk>/supprimer/', StockDeleteView.as_view(), name='stock_delete'),
    

    # Ajustements
    path('ajustements/nouveau/', AjustementStockCreateView.as_view(), name='ajustement_create'),
    
    # API
    path('api/stock-disponible/', get_stock_disponible, name='stock_disponible'),
    path('api/stocks-expires/', stocks_expires_bientot, name='stocks_expires'),

    # Achats
    # path("achats/", views.AchatListView.as_view(), name="achat_list"),
    # path("achats/create/", views.AchatCreateView.as_view(), name="achat_create"),
    # path("achats/<int:pk>/edit/", views.AchatUpdateView.as_view(), name="achat_update"),
    # path("achats/<int:pk>/", views.AchatDetailView.as_view(), name="achat_detail"),
    # path(
    #     "achats/<int:pk>/delete/", views.AchatDeleteView.as_view(), name="achat_delete"
    # ),
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
    # OrdrePaiement CRUD
    path(
        "commandes/<int:commande_pk>/ordres/add/",
        OrdrePaiementCreateView.as_view(),
        name="ordre_add",
    ),
    path(
        "ordres/<int:pk>/update/",
        OrdrePaiementUpdateView.as_view(),
        name="ordre_update",
    ),
    # Bons de commande
    path("commandes/", views.BonCommandeListView.as_view(), name="commande_list"),
    path(
        "commandes/creer/",
        views.BonCommandeCreateView.as_view(),
        name="commande_create",
    ),
    path(
        "commandes/<int:pk>/",
        views.BonCommandeDetailView.as_view(),
        name="commande_detail",
    ),
    path(
        "commandes/<int:pk>/modifier/",
        views.BonCommandeUpdateView.as_view(),
        name="commande_update",
    ),
    path(
        "commandes/<int:pk>/supprimer/",
        views.BonCommandeDeleteView.as_view(),
        name="commande_delete",
    ),
    # pharmacies/urls.py
    path(
        "commandes/<int:pk>/statut/",
        views.BonCommandeUpdateStatutView.as_view(),
        name="commande_update_statut",
    ),
    # Livraisons
    path("livraisons/", views.BonLivraisonListView.as_view(), name="livraison_list"),
    path(
        "livraisons/<int:pk>/",
        views.BonLivraisonDetailView.as_view(),
        name="livraison_detail",
    ),
    path(
        "commandes/<int:commande_pk>/livraison/creer/",
        views.BonLivraisonCreateView.as_view(),
        name="livraison_create",
    ),
    path(
        "livraisons/<int:pk>/valider/",
        views.ValiderLivraisonView.as_view(),
        name="livraison_valider",
    ),
    # Documents
    path(
        "commandes/<int:pk>/pdf/",
        views.GenererPDFCommandeView.as_view(),
        name="commande_pdf",
    ),
]
