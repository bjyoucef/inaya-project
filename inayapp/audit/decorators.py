# audit/decorators.py
from functools import wraps
from django.contrib.contenttypes.models import ContentType
from .utils import create_audit_log, get_current_user


def audit_action(action_name, get_object=None):
    """Décorateur pour auditer des actions personnalisées"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Tenter d'obtenir l'objet depuis les arguments ou le résultat
            obj = None
            if get_object:
                obj = get_object(*args, **kwargs)
            elif hasattr(result, "pk"):
                obj = result
            elif args and hasattr(args[0], "pk"):
                obj = args[0]

            if obj:
                create_audit_log(obj, action_name)

            return result

        return wrapper

    return decorator


def audit_view(view_func):
    """Décorateur pour auditer l'accès aux vues"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)

        # Créer un log d'audit pour la vue
        from .models import AuditLog
        from .utils import get_client_ip, get_user_agent

        if request.user.is_authenticated:
            AuditLog.objects.create(
                user=request.user,
                username=request.user.username,
                action="VIEW",
                url=request.get_full_path(),
                method=request.method,
                status_code=getattr(response, "status_code", 200),
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                object_repr=f"Vue: {view_func.__name__}",
            )

        return response

    return wrapper
