from django.urls import path


from . import views


urlpatterns = [
    path("planning", views.planning, name="planning"),
    path("save-planning/", views.save_planning, name="save_planning"),
    path("update-event/", views.update_event, name="update_event"),
    path("delete-event/<int:event_id>/", views.delete_event, name="delete_event"),
    path("planning/print/", views.print_planning, name="print_planning"),
    path("print-planning/", views.print_planning, name="print_planning"),
    path(
        "validate-presence/<int:event_id>/",
        views.validate_presence,
        name="validate_presence",
    ),
    path(
        "validate-presence-range/",
        views.validate_presence_range,
        name="validate_presence_range",
    ),
    path("sync/attendances/", views.sync_attendances, name="sync_attendances"),
    path("sync/users/", views.sync_users, name="sync_users"),
    path("pointages/", views.rapport_pointage, name="attendance_report"),
    path(
        "save-reference-hours/", views.save_reference_hours, name="save_reference_hours"
    ),
    path("pointages/salary-config/", views.salary_config_view, name="salary_config"),
    path("save-salary-config/", views.handle_config_save, name="save_salary_config"),
    path(
        "salary-advance/create/",
        views.salary_advance_create,
        name="salary_advance_create",
    ),
    path(
        "leave-request/create/", views.leave_request_create, name="leave_request_create"
    ),
    path("demandes/", views.demandes, name="demandes"),
    path(
        "salary-request/<int:request_id>/<str:action>/",
        views.process_salary_request,
        name="process_salary_request",
    ),
    path(
        "leave-request/<int:request_id>/<str:action>/",
        views.process_leave_request,
        name="process_leave_request",
    ),
    path("get-honoraires-acte/", views.get_honoraires_acte, name="get_honoraires_acte"),
    path("add-pointage-acte/", views.add_pointage_acte, name="add_pointage_acte"),
]

urlpatterns += [
    # Liste des demandes
    path(
        "demandes/heures-sup/",
        views.liste_demandes_heures_sup,
        name="liste_demandes_heures_sup",
    ),
    # Créer une demande
    path(
        "demandes/heures-sup/creer/",
        views.creer_demande_heures_sup,
        name="creer_demande_heures_sup",
    ),
    # Détails d'une demande
    path(
        "demandes/heures-sup/<int:pk>/",
        views.detail_demande_heures_sup,
        name="detail_demande_heures_sup",
    ),
    # Modifier une demande
    path(
        "demandes/heures-sup/<int:pk>/modifier/",
        views.modifier_demande_heures_sup,
        name="modifier_demande_heures_sup",
    ),
    # Valider une demande
    path(
        "<int:pk>/valider/",
        views.valider_demande_heures_sup,
        name="valider_demande_heures_sup",
    ),
    # Annuler une demande
    path(
        "<int:pk>/annuler/",
        views.annuler_demande_heures_sup,
        name="annuler_demande_heures_sup",
    ),
    # AJAX pour calcul d'heures
    path("ajax/calcul-heures/", views.calcul_heures_ajax, name="calcul_heures_ajax"),
]


urlpatterns += [
    path(
        "get_available_advance_amount/",
        views.get_available_advance_amount,
        name="get_available_advance_amount",
    ),
    path(
        "get_remaining_leave_days/",
        views.get_remaining_leave_days,
        name="get_remaining_leave_days",
    ),

]
