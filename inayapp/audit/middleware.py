# audit/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver
from .models import AuditLog, LoginAttempt
from .utils import get_client_ip, get_user_agent
import threading

# Thread local pour stocker les informations de la requête
_thread_local = threading.local()


class AuditMiddleware(MiddlewareMixin):
    """Middleware pour capturer les informations de requête pour l'audit"""

    def process_request(self, request):
        _thread_local.request = request
        return None

    def process_response(self, request, response):
        # Enregistrer l'accès à la page si configuré
        if hasattr(request, "user") and request.user.is_authenticated:
            if self.should_audit_view(request):
                AuditLog.objects.create(
                    user=request.user,
                    username=request.user.username,
                    action="VIEW",
                    url=request.get_full_path(),
                    method=request.method,
                    status_code=response.status_code,
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                    session_key=request.session.session_key,
                )

        return response

    def should_audit_view(self, request):
        """Détermine si la vue doit être auditée"""
        # Éviter d'auditer les requêtes AJAX, les ressources statiques, etc.
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return False
        if request.path.startswith("/static/"):
            return False
        if request.path.startswith("/media/"):
            return False
        if request.path.startswith("/admin/jsi18n/"):
            return False
        return True


# Signaux pour les connexions/déconnexions
@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    LoginAttempt.objects.create(
        username=user.username,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        successful=True,
    )

    AuditLog.objects.create(
        user=user,
        username=user.username,
        action="LOGIN",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        session_key=request.session.session_key,
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        AuditLog.objects.create(
            user=user,
            username=user.username,
            action="LOGOUT",
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            session_key=request.session.session_key,
        )


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    username = credentials.get("username", "")

    LoginAttempt.objects.create(
        username=username,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        successful=False,
        failure_reason="Identifiants invalides",
    )

    AuditLog.objects.create(
        username=username,
        action="FAILED_LOGIN",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
