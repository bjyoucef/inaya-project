# audit/context_processors.py
def audit_stats(request):
    """Processeur de contexte pour afficher des stats d'audit"""
    if not request.user.is_authenticated or not request.user.is_staff:
        return {}

    from .models import AuditLog
    from django.utils import timezone
    from datetime import timedelta

    # Stats des dernières 24h
    last_24h = timezone.now() - timedelta(hours=24)

    return {
        "audit_stats": {
            "logs_today": AuditLog.objects.filter(timestamp__gte=last_24h).count(),
            "user_actions_today": (
                AuditLog.objects.filter(
                    timestamp__gte=last_24h, user=request.user
                ).count()
                if request.user.is_authenticated
                else 0
            ),
        }
    }
