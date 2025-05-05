# pharmacies/urls.py
from django.urls import path
from . import views

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
    path("stocks/", views.StockListView.as_view(), name="stock_list"),
    path("stocks/create/", views.StockCreateView.as_view(), name="stock_create"),
    # Transferts
    path("transferts/", views.TransfertListView.as_view(), name="transfert_list"),
    path(
        "transferts/create/",
        views.TransfertCreateView.as_view(),
        name="transfert_create",
    ),
    # # Achats
    # path("achats/", views.AchatListView.as_view(), name="achat_list"),
    # path("achats/create/", views.AchatCreateView.as_view(), name="achat_create"),
    # path("achats/<int:pk>/edit/", views.AchatUpdateView.as_view(), name="achat_update"),
    # path("achats/<int:pk>/", views.AchatDetailView.as_view(), name="achat_detail"),
    # path(
    #     "achats/<int:pk>/delete/", views.AchatDeleteView.as_view(), name="achat_delete"
    # ),
    # Fournisseur
    path("fournisseurs", views.FournisseurListView.as_view(), name="liste"),
    path("fournisseurs/creer/", views.FournisseurCreateView.as_view(), name="creer"),
    path(
        "fournisseurs/<int:pk>/", views.FournisseurDetailView.as_view(), name="detail"
    ),
    path(
        "fournisseurs/<int:pk>/modifier/",
        views.FournisseurUpdateView.as_view(),
        name="modifier",
    ),
    path(
        "fournisseurs/<int:pk>/supprimer/",
        views.FournisseurDeleteView.as_view(),
        name="supprimer",
    ),
    path(
        "fournisseurs/<int:pk>/paiements/creer/",
        views.PaiementCreateView.as_view(),
        name="creer_paiement",
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
    # Livraisons
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
    # Paiements
    path(
        "commandes/<int:commande_pk>/paiement/creer/",
        views.OrdrePaiementCreateView.as_view(),
        name="paiement_create",
    ),
    path(
        "paiements/<int:pk>/annuler/",
        views.AnnulerPaiementView.as_view(),
        name="paiement_annuler",
    ),
    # Documents
    path(
        "commandes/<int:pk>/pdf/",
        views.GenererPDFCommandeView.as_view(),
        name="commande_pdf",
    ),
]
