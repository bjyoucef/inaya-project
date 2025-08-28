from django.urls import path
from . import views

urlpatterns = [
    path(
        "add-decharge-multiple/",
        views.add_decharge_multiple,
        name="add_decharge_multiple",
    ),
    path(
        "situation-medecin/<int:medecin_id>/create-decharge/",
        views.create_decharge_medecin,
        name="create_decharge",
    ),
    path("decharge/", views.decharge_list, name="decharge_list"),
    path("decharge/reglees/", views.decharge_settled, name="decharge_settled"),
    path("decharge/create/", views.decharge_create, name="decharge_create"),
    path("decharge/<int:pk>/", views.decharge_detail, name="decharge_detail"),
    path("decharge/<int:pk>/edit/", views.decharge_edit, name="decharge_edit"),
    path("decharge/<int:pk>/delete/", views.decharge_delete, name="decharge_delete"),
    path(
        "decharge/payment/<int:pk>/delete/", views.payment_delete, name="payment_delete"
    ),
    path(
        "decharges/<int:decharge_id>/export/",
        views.export_decharge_pdf,
        name="export_decharge_pdf",
    ),
    path(
        "decharges/<int:decharge_id>/print/",
        views.print_decharge_view,
        name="print_decharge",
    ),
    path(
        "situation-medecin/",
        views.situation_medecins_list,
        name="situation_medecins_list",
    ),
    path(
        "situation-medecin/<int:medecin_id>/",
        views.situation_medecin,
        name="situation_medecin",
    ),
    #######################################
    # Facturation
    path(
        "conventions-status/",
        views.gestion_convention_accorde_dossier,
        name="gestion_convention_accorde_dossier",
    ),
    path(
        "conventions-status/<int:pk>/update/",
        views.update_convention_status,
        name="update_convention_status",
    ),
    # Actes facturés
    path(
        "conventions-status/tableau-bord/",
        views.tableau_bord_facturation,
        name="tableau_bord_facturation",
    ),
    # Gestion des actes
    path(
        "conventions-status/facturation/",
        views.actes_a_facturer,
        name="actes_a_facturer",
    ),
    path(
        "conventions-status/facturation/actes-factures/",
        views.actes_factures,
        name="actes_factures",
    ),
    path(
        "conventions-status/facturation/actes-payes/",
        views.actes_payes,
        name="actes_payes",
    ),
    path(
        "conventions-status/facturation/actes-rejetes/",
        views.actes_rejetes,
        name="actes_rejetes",
    ),
    # Actions sur les actes
    path(
        "conventions-status/facturation/facturer-acte/<int:acte_id>/",
        views.facturer_acte,
        name="facturer_acte",
    ),
    path(
        "conventions-status/facturation/marquer-paye-acte/<int:acte_id>/",
        views.marquer_paye_acte,
        name="marquer_paye_acte",
    ),
    path(
        "conventions-status/facturation/rejeter-acte/<int:acte_id>/",
        views.rejeter_acte,
        name="rejeter_acte",
    ),
    #################################
    # URLs pour le suivi des paiements espèces
    path(
        "paiement-especes-kt/",
        views.PrestationsEspecesEnAttenteView.as_view(),
        name="prestations_especes_en_attente",
    ),
    path(
        "paiement-especes-kt/payees/",
        views.PrestationsEspecesPayeesView.as_view(),
        name="prestations_especes_payees",
    ),
    path(
        "paiement-especes-kt/dashboard/",
        views.DashboardPaiementsEspecesView.as_view(),
        name="dashboard_paiements_especes",
    ),
    # Nouvelles URLs pour la gestion Ajax des paiements
    path(
        "paiement-especes-kt/<int:prestation_id>/paiement-especes/",
        views.GestionPaiementEspecesView.as_view(),
        name="gestion_paiement_especes",
    ),
    path(
        "paiement-especes-kt/tranches/<int:tranche_id>/",
        views.SupprimerTranchePaiementView.as_view(),
        name="supprimer_tranche_paiement",
    ),
]
