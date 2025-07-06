# audit/utils.py
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog, AuditConfiguration
import threading

_thread_local = threading.local()


def get_client_ip(request):
    """Obtient l'adresse IP réelle du client"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def get_user_agent(request):
    """Obtient le User-Agent du client"""
    return request.META.get("HTTP_USER_AGENT", "")


def get_current_request():
    """Obtient la requête courante depuis le thread local"""
    return getattr(_thread_local, "request", None)


def get_current_user():
    """Obtient l'utilisateur courant depuis la requête"""
    request = get_current_request()
    if request and hasattr(request, "user") and request.user.is_authenticated:
        return request.user
    return None


def create_audit_log(instance, action, changes=None):
    """Crée un log d'audit pour une instance"""
    request = get_current_request()
    user = get_current_user()

    content_type = ContentType.objects.get_for_model(instance)

    # Vérifier si l'audit est activé pour ce modèle
    try:
        config = AuditConfiguration.objects.get(content_type=content_type)
        if not config.is_active:
            return

        # Vérifier si cette action spécifique est trackée
        if action == "CREATE" and not config.track_create:
            return
        elif action == "UPDATE" and not config.track_update:
            return
        elif action == "DELETE" and not config.track_delete:
            return
        elif action == "VIEW" and not config.track_view:
            return
    except AuditConfiguration.DoesNotExist:
        # Si pas de configuration, on audit par défaut
        pass

    audit_data = {
        "user": user,
        "username": user.username if user else "",
        "action": action,
        "content_type": content_type,
        "object_id": instance.pk if hasattr(instance, "pk") else None,
        "object_repr": str(instance),
        "changes": changes or {},
        "app_label": content_type.app_label,
        "model_name": content_type.model,
    }

    if request:
        audit_data.update(
            {
                "ip_address": get_client_ip(request),
                "user_agent": get_user_agent(request),
                "session_key": request.session.session_key,
                "url": request.get_full_path(),
                "method": request.method,
            }
        )

    AuditLog.objects.create(**audit_data)


def get_model_changes(old_instance, new_instance, excluded_fields=None):
    """Compare deux instances et retourne les changements"""
    if excluded_fields is None:
        excluded_fields = []

    changes = {}

    # Obtenir tous les champs du modèle
    for field in new_instance._meta.fields:
        field_name = field.name

        if field_name in excluded_fields:
            continue

        old_value = getattr(old_instance, field_name, None) if old_instance else None
        new_value = getattr(new_instance, field_name, None)

        if old_value != new_value:
            changes[field_name] = {
                "old": str(old_value) if old_value is not None else None,
                "new": str(new_value) if new_value is not None else None,
            }

    return changes
