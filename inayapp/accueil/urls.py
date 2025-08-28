from django.urls import path, include
from .views import ajax_toggle_permission, group_permissions_detail, group_permissions_list, home, update_user_permissions, user_permissions_detail, user_permissions_list
from . import views

urlpatterns = [
    path("", home, name="home"),
    # Gestion des permissions utilisateur

    path(
        "permissions/dashboard/",
        views.permissions_dashboard,
        name="permissions_dashboard",
    ),
    # Gestion des utilisateurs
    path(
        "permissions/users/", views.user_permissions_list, name="user_permissions_list"
    ),
    path(
        "permissions/users/<int:user_id>/",
        views.user_permissions_detail,
        name="user_permissions_detail",
    ),
    path(
        "permissions/users/<int:user_id>/update/",
        views.update_user_permissions,
        name="update_user_permissions",
    ),
    # Gestion des groupes
    path(
        "permissions/groups/",
        views.group_permissions_list,
        name="group_permissions_list",
    ),
    path(
        "permissions/groups/<int:group_id>/",
        views.group_permissions_detail,
        name="group_permissions_detail",
    ),
    # AJAX (optionnel)
    path(
        "permissions/ajax/toggle/",
        views.ajax_toggle_permission,
        name="ajax_toggle_permission",
    ),
]
