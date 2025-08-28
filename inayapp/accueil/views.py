import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@require_POST
@login_required
def update_theme(request):
    try:
        data = json.loads(request.body)
        theme = data.get("theme")

        if theme not in ["light", "dark"]:
            return JsonResponse(
                {"status": "error", "message": "Valeur de thème invalide"}, status=400
            )

        # Mise à jour du thème
        theme_obj = request.user.theme
        theme_obj.theme = theme
        theme_obj.save()

        return JsonResponse({"status": "success", "theme": theme})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


def home(request):
    # On récupère les messages pour les afficher dans le template
    msg_list = list(messages.get_messages(request))
    for msg in msg_list:
        if "success" in msg.tags:
            msg.bg_color = "linear-gradient(to right, #00b09b, #96c93d)"
        else:
            msg.bg_color = "linear-gradient(to right, #f85032, #e73827)"
    return render(request, 'home.html', {'messages': msg_list})


# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User, Permission, Group
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Q


@login_required
@permission_required("auth.change_user", raise_exception=True)
def user_permissions_list(request):
    """Vue pour lister tous les utilisateurs avec leurs permissions"""
    search_query = request.GET.get("search", "")
    users = User.objects.all()

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "total_users": users.count(),
    }

    return render(request, "permissions/user_list.html", context)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def user_permissions_detail(request, user_id):
    """Vue pour afficher et modifier les permissions d'un utilisateur spécifique"""
    user = get_object_or_404(User, id=user_id)

    # Récupérer toutes les permissions disponibles
    all_permissions = Permission.objects.select_related("content_type").all()

    # Grouper les permissions par modèle
    permissions_by_model = {}
    for perm in all_permissions:
        model_name = perm.content_type.model
        app_label = perm.content_type.app_label
        key = f"{app_label}.{model_name}"

        if key not in permissions_by_model:
            permissions_by_model[key] = {
                "model_name": model_name.title(),
                "app_label": app_label,
                "permissions": [],
            }
        permissions_by_model[key]["permissions"].append(perm)

    # Permissions actuelles de l'utilisateur
    user_permissions = set(user.user_permissions.all()) | set(
        user.get_group_permissions()
    )
    user_permission_ids = set(user.user_permissions.values_list("id", flat=True))

    # Groupes disponibles
    all_groups = Group.objects.all()
    user_groups = user.groups.all()

    context = {
        "user": user,
        "permissions_by_model": permissions_by_model,
        "user_permission_ids": user_permission_ids,
        "all_groups": all_groups,
        "user_groups": user_groups,
    }

    return render(request, "permissions/user_permissions_detail.html", context)


@login_required
@permission_required("auth.change_user", raise_exception=True)
@require_http_methods(["POST"])
def update_user_permissions(request, user_id):
    """Vue pour mettre à jour les permissions d'un utilisateur"""
    user = get_object_or_404(User, id=user_id)

    # Récupérer les permissions sélectionnées
    selected_permissions = request.POST.getlist("permissions")
    selected_groups = request.POST.getlist("groups")

    try:
        # Mettre à jour les permissions individuelles
        user.user_permissions.clear()
        if selected_permissions:
            permissions = Permission.objects.filter(id__in=selected_permissions)
            user.user_permissions.set(permissions)

        # Mettre à jour les groupes
        user.groups.clear()
        if selected_groups:
            groups = Group.objects.filter(id__in=selected_groups)
            user.groups.set(groups)

        # Mettre à jour le statut staff et superuser si nécessaire
        is_staff = request.POST.get("is_staff") == "on"
        is_superuser = request.POST.get("is_superuser") == "on"

        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save()

        messages.success(
            request,
            f"Les permissions de {user.username} ont été mises à jour avec succès.",
        )

    except Exception as e:
        messages.error(request, f"Erreur lors de la mise à jour : {str(e)}")

    return redirect("user_permissions_detail", user_id=user_id)


@login_required
@permission_required("auth.add_group", raise_exception=True)
def group_permissions_list(request):
    """Vue pour gérer les groupes et leurs permissions"""
    groups = Group.objects.prefetch_related("permissions").all()

    context = {
        "groups": groups,
    }

    return render(request, "permissions/group_list.html", context)


@login_required
@permission_required("auth.change_group", raise_exception=True)
def group_permissions_detail(request, group_id):
    """Vue pour modifier les permissions d'un groupe"""
    group = get_object_or_404(Group, id=group_id)

    if request.method == "POST":
        selected_permissions = request.POST.getlist("permissions")

        try:
            group.permissions.clear()
            if selected_permissions:
                permissions = Permission.objects.filter(id__in=selected_permissions)
                group.permissions.set(permissions)

            messages.success(
                request,
                f'Les permissions du groupe "{group.name}" ont été mises à jour.',
            )
            return redirect("group_permissions_list")

        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour : {str(e)}")

    # Récupérer toutes les permissions disponibles
    all_permissions = Permission.objects.select_related("content_type").all()
    group_permission_ids = set(group.permissions.values_list("id", flat=True))

    # Grouper les permissions par modèle
    permissions_by_model = {}
    for perm in all_permissions:
        model_name = perm.content_type.model
        app_label = perm.content_type.app_label
        key = f"{app_label}.{model_name}"

        if key not in permissions_by_model:
            permissions_by_model[key] = {
                "model_name": model_name.title(),
                "app_label": app_label,
                "permissions": [],
            }
        permissions_by_model[key]["permissions"].append(perm)

    context = {
        "group": group,
        "permissions_by_model": permissions_by_model,
        "group_permission_ids": group_permission_ids,
    }

    return render(request, "permissions/group_permissions_detail.html", context)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def ajax_toggle_permission(request):
    """Vue AJAX pour basculer rapidement une permission"""
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        permission_id = request.POST.get("permission_id")
        action = request.POST.get("action")  # 'add' ou 'remove'

        try:
            user = User.objects.get(id=user_id)
            permission = Permission.objects.get(id=permission_id)

            if action == "add":
                user.user_permissions.add(permission)
                message = f'Permission "{permission.name}" ajoutée à {user.username}'
            else:
                user.user_permissions.remove(permission)
                message = f'Permission "{permission.name}" supprimée de {user.username}'

            return JsonResponse({"success": True, "message": message})

        except (User.DoesNotExist, Permission.DoesNotExist) as e:
            return JsonResponse(
                {"success": False, "message": "Utilisateur ou permission introuvable"}
            )
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Erreur : {str(e)}"})

    return JsonResponse({"success": False, "message": "Méthode non autorisée"})


# Dans votre views.py (créez un fichier permissions/views.py si nécessaire)

from django.shortcuts import render
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User, Group, Permission
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType


@permission_required(["auth.view_user", "auth.view_group"], raise_exception=True)
def permissions_dashboard(request):
    """Vue dashboard pour un aperçu global des permissions"""

    # Statistiques générales
    stats = {
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "staff_users": User.objects.filter(is_staff=True).count(),
        "superusers": User.objects.filter(is_superuser=True).count(),
        "total_groups": Group.objects.count(),
        "total_permissions": Permission.objects.count(),
    }

    # Groupes les plus utilisés
    popular_groups = Group.objects.annotate(user_count=Count("user")).order_by(
        "-user_count"
    )[:5]

    # Applications avec leurs permissions
    apps_permissions = {}
    for ct in ContentType.objects.all():
        app_label = ct.app_label
        if app_label not in apps_permissions:
            apps_permissions[app_label] = {
                "name": app_label.title(),
                "models": [],
                "total_permissions": 0,
            }

        model_perms = Permission.objects.filter(content_type=ct)
        apps_permissions[app_label]["models"].append(
            {"name": ct.model, "permissions_count": model_perms.count()}
        )
        apps_permissions[app_label]["total_permissions"] += model_perms.count()

    # Utilisateurs récents
    recent_users = User.objects.filter(is_active=True).order_by("-date_joined")[:5]

    context = {
        "stats": stats,
        "popular_groups": popular_groups,
        "apps_permissions": apps_permissions,
        "recent_users": recent_users,
    }

    return render(request, "permissions/dashboard.html", context)
