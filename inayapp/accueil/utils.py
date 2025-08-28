# utils.py
from django.contrib.auth.models import User, Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Count
from collections import defaultdict
import json
import csv
from io import StringIO
from django.http import HttpResponse


class PermissionManager:
    """Gestionnaire utilitaire pour les permissions"""

    @staticmethod
    def get_permissions_by_model():
        """Retourne les permissions groupées par modèle"""
        permissions = Permission.objects.select_related("content_type").all()
        permissions_by_model = defaultdict(list)

        for perm in permissions:
            key = f"{perm.content_type.app_label}.{perm.content_type.model}"
            permissions_by_model[key].append(perm)

        return dict(permissions_by_model)

    @staticmethod
    def get_user_all_permissions(user):
        """Retourne toutes les permissions d'un utilisateur (directes + groupes)"""
        if user.is_superuser:
            return Permission.objects.all()

        # Permissions directes
        direct_perms = user.user_permissions.all()

        # Permissions via les groupes
        group_perms = Permission.objects.filter(group__user=user)

        # Union des deux
        all_perms = direct_perms.union(group_perms)

        return all_perms

    @staticmethod
    def compare_user_permissions(users):
        """Compare les permissions entre plusieurs utilisateurs"""
        if not users:
            return {}

        user_permissions = {}
        all_permissions = set()

        for user in users:
            perms = set(PermissionManager.get_user_all_permissions(user))
            user_permissions[user] = perms
            all_permissions.update(perms)

        # Permissions communes à tous
        common_permissions = (
            set.intersection(*user_permissions.values()) if user_permissions else set()
        )

        # Permissions uniques à chaque utilisateur
        unique_permissions = {}
        for user, perms in user_permissions.items():
            unique = perms - set.union(
                *[p for u, p in user_permissions.items() if u != user]
            )
            unique_permissions[user] = unique

        return {
            "user_permissions": user_permissions,
            "common_permissions": common_permissions,
            "unique_permissions": unique_permissions,
            "all_permissions": all_permissions,
        }

    @staticmethod
    def get_permission_statistics():
        """Retourne des statistiques sur les permissions"""
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        staff_users = User.objects.filter(is_staff=True).count()
        superusers = User.objects.filter(is_superuser=True).count()

        total_groups = Group.objects.count()
        total_permissions = Permission.objects.count()

        # Permissions les plus utilisées
        popular_permissions = Permission.objects.annotate(
            usage_count=Count("user") + Count("group")
        ).order_by("-usage_count")[:10]

        # Groupes les plus populaires
        popular_groups = Group.objects.annotate(user_count=Count("user")).order_by(
            "-user_count"
        )[:10]

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "staff": staff_users,
                "superusers": superusers,
            },
            "groups": {
                "total": total_groups,
            },
            "permissions": {
                "total": total_permissions,
                "popular": popular_permissions,
            },
            "popular_groups": popular_groups,
        }

    @staticmethod
    def bulk_assign_permissions(users, permissions, action="add"):
        """Assigne des permissions en masse"""
        results = {"success": 0, "errors": []}

        for user in users:
            try:
                if action == "add":
                    user.user_permissions.add(*permissions)
                elif action == "remove":
                    user.user_permissions.remove(*permissions)
                results["success"] += 1
            except Exception as e:
                results["errors"].append(f"Erreur pour {user.username}: {str(e)}")

        return results

    @staticmethod
    def bulk_assign_groups(users, groups, action="add"):
        """Assigne des groupes en masse"""
        results = {"success": 0, "errors": []}

        for user in users:
            try:
                if action == "add":
                    user.groups.add(*groups)
                elif action == "remove":
                    user.groups.remove(*groups)
                results["success"] += 1
            except Exception as e:
                results["errors"].append(f"Erreur pour {user.username}: {str(e)}")

        return results


class PermissionExporter:
    """Classe pour exporter les permissions"""

    @staticmethod
    def export_to_csv(users=None, groups=None):
        """Exporte les permissions au format CSV"""
        output = StringIO()
        writer = csv.writer(output)

        # En-têtes
        headers = [
            "Type",
            "Nom",
            "Email",
            "Actif",
            "Staff",
            "Superuser",
            "Groupes",
            "Permissions",
        ]
        writer.writerow(headers)

        # Utilisateurs
        if users:
            for user in users:
                groups_list = ", ".join([g.name for g in user.groups.all()])
                perms_list = ", ".join(
                    [
                        f"{p.content_type.app_label}.{p.codename}"
                        for p in user.user_permissions.all()
                    ]
                )

                writer.writerow(
                    [
                        "Utilisateur",
                        user.get_full_name() or user.username,
                        user.email,
                        "Oui" if user.is_active else "Non",
                        "Oui" if user.is_staff else "Non",
                        "Oui" if user.is_superuser else "Non",
                        groups_list,
                        perms_list,
                    ]
                )

        # Groupes
        if groups:
            for group in groups:
                perms_list = ", ".join(
                    [
                        f"{p.content_type.app_label}.{p.codename}"
                        for p in group.permissions.all()
                    ]
                )
                users_count = group.user_set.count()

                writer.writerow(
                    [
                        "Groupe",
                        group.name,
                        "",
                        "",
                        "",
                        "",
                        f"{users_count} utilisateurs",
                        perms_list,
                    ]
                )

        return output.getvalue()

    @staticmethod
    def export_to_json(users=None, groups=None):
        """Exporte les permissions au format JSON"""
        data = {"export_date": str(timezone.now()), "users": [], "groups": []}

        # Utilisateurs
        if users:
            for user in users:
                user_data = {
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "groups": [g.name for g in user.groups.all()],
                    "permissions": [
                        f"{p.content_type.app_label}.{p.codename}"
                        for p in user.user_permissions.all()
                    ],
                }
                data["users"].append(user_data)

        # Groupes
        if groups:
            for group in groups:
                group_data = {
                    "name": group.name,
                    "permissions": [
                        f"{p.content_type.app_label}.{p.codename}"
                        for p in group.permissions.all()
                    ],
                    "users_count": group.user_set.count(),
                }
                data["groups"].append(group_data)

        return json.dumps(data, indent=2, ensure_ascii=False)


class PermissionTemplates:
    """Templates prédéfinis de permissions"""

    TEMPLATES = {
        "admin": {
            "name": "Administrateur",
            "description": "Accès complet à l'administration",
            "permissions": [
                "auth.add_user",
                "auth.change_user",
                "auth.delete_user",
                "auth.view_user",
                "auth.add_group",
                "auth.change_group",
                "auth.delete_group",
                "auth.view_group",
                "auth.add_permission",
                "auth.change_permission",
                "auth.delete_permission",
                "auth.view_permission",
            ],
            "is_staff": True,
            "is_superuser": False,
        },
        "editor": {
            "name": "Éditeur",
            "description": "Peut créer et modifier du contenu",
            "permissions": [
                "auth.view_user",
                "auth.view_group",
                # Ajouter ici les permissions spécifiques au contenu
            ],
            "is_staff": True,
            "is_superuser": False,
        },
        "viewer": {
            "name": "Lecteur",
            "description": "Accès en lecture seule",
            "permissions": [
                "auth.view_user",
                "auth.view_group",
            ],
            "is_staff": False,
            "is_superuser": False,
        },
        "moderator": {
            "name": "Modérateur",
            "description": "Peut modérer le contenu",
            "permissions": [
                "auth.view_user",
                "auth.change_user",
                "auth.view_group",
            ],
            "is_staff": True,
            "is_superuser": False,
        },
    }

    @classmethod
    def apply_template(cls, user, template_name):
        """Applique un template à un utilisateur"""
        if template_name not in cls.TEMPLATES:
            raise ValueError(f"Template '{template_name}' non trouvé")

        template = cls.TEMPLATES[template_name]

        # Définir le statut
        user.is_staff = template.get("is_staff", False)
        user.is_superuser = template.get("is_superuser", False)
        user.save()

        # Assigner les permissions
        permissions = Permission.objects.filter(
            codename__in=[p.split(".")[-1] for p in template["permissions"]],
            content_type__app_label__in=[
                p.split(".")[0] for p in template["permissions"]
            ],
        )
        user.user_permissions.set(permissions)

        return True

    @classmethod
    def get_template_permissions(cls, template_name):
        """Retourne les permissions d'un template"""
        if template_name not in cls.TEMPLATES:
            return []

        template = cls.TEMPLATES[template_name]
        permissions = []

        for perm_code in template["permissions"]:
            app_label, codename = perm_code.split(".")
            try:
                content_type = ContentType.objects.get(app_label=app_label)
                permission = Permission.objects.get(
                    content_type=content_type, codename=codename
                )
                permissions.append(permission)
            except (ContentType.DoesNotExist, Permission.DoesNotExist):
                continue

        return permissions


class PermissionValidator:
    """Validateur de permissions"""

    @staticmethod
    def validate_user_permissions(user):
        """Valide les permissions d'un utilisateur"""
        issues = []

        # Vérifier si l'utilisateur est superuser mais pas staff
        if user.is_superuser and not user.is_staff:
            issues.append("L'utilisateur est superuser mais pas staff")

        # Vérifier les permissions orphelines
        invalid_permissions = []
        for perm in user.user_permissions.all():
            try:
                # Tenter d'accéder au content_type
                _ = perm.content_type.model_class()
            except:
                invalid_permissions.append(perm)

        if invalid_permissions:
            issues.append(
                f"Permissions orphelines: {[p.codename for p in invalid_permissions]}"
            )

        # Vérifier les doublons entre permissions directes et de groupe
        direct_perms = set(user.user_permissions.all())
        group_perms = set()
        for group in user.groups.all():
            group_perms.update(group.permissions.all())

        duplicates = direct_perms.intersection(group_perms)
        if duplicates:
            issues.append(f"Permissions dupliquées: {[p.codename for p in duplicates]}")

        return issues

    @staticmethod
    def audit_permissions():
        """Audit complet des permissions du système"""
        report = {"users": {}, "groups": {}, "global_issues": []}

        # Audit des utilisateurs
        for user in User.objects.all():
            issues = PermissionValidator.validate_user_permissions(user)
            if issues:
                report["users"][user.username] = issues

        # Audit des groupes
        for group in Group.objects.all():
            issues = []

            # Vérifier les permissions orphelines
            invalid_permissions = []
            for perm in group.permissions.all():
                try:
                    _ = perm.content_type.model_class()
                except:
                    invalid_permissions.append(perm)

            if invalid_permissions:
                issues.append(
                    f"Permissions orphelines: {[p.codename for p in invalid_permissions]}"
                )

            if issues:
                report["groups"][group.name] = issues

        # Issues globales
        # Permissions inutilisées
        unused_perms = Permission.objects.filter(user__isnull=True, group__isnull=True)
        if unused_perms.exists():
            report["global_issues"].append(
                f"Permissions non utilisées: {unused_perms.count()}"
            )

        return report
