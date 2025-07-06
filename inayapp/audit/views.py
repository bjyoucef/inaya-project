# audit/views.py
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import AuditLog, LoginAttempt
from django.http import JsonResponse
import json


@staff_member_required
def audit_dashboard(request):
    """Tableau de bord d'audit"""
    # Statistiques des dernières 24h
    last_24h = timezone.now() - timedelta(hours=24)

    stats = {
        "total_logs": AuditLog.objects.count(),
        "logs_24h": AuditLog.objects.filter(timestamp__gte=last_24h).count(),
        "unique_users_24h": AuditLog.objects.filter(timestamp__gte=last_24h)
        .values("user")
        .distinct()
        .count(),
        "failed_logins_24h": LoginAttempt.objects.filter(
            timestamp__gte=last_24h, successful=False
        ).count(),
    }

    # Actions les plus fréquentes
    top_actions = (
        AuditLog.objects.values("action")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Utilisateurs les plus actifs
    top_users = (
        AuditLog.objects.filter(timestamp__gte=last_24h)
        .values("username")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Logs récents
    recent_logs = AuditLog.objects.select_related("user", "content_type").order_by(
        "-timestamp"
    )[:20]

    context = {
        "stats": stats,
        "top_actions": top_actions,
        "top_users": top_users,
        "recent_logs": recent_logs,
    }

    return render(request, "dashboard.html", context)


@staff_member_required
def audit_api_stats(request):
    """API pour les statistiques d'audit (pour les graphiques)"""
    days = int(request.GET.get("days", 7))
    start_date = timezone.now() - timedelta(days=days)

    # Logs par jour
    logs_by_day = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)

        count = AuditLog.objects.filter(
            timestamp__gte=date_start, timestamp__lt=date_end
        ).count()

        logs_by_day.append({"date": date.strftime("%Y-%m-%d"), "count": count})

    # Actions par type
    actions_by_type = list(
        AuditLog.objects.filter(timestamp__gte=start_date)
        .values("action")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return JsonResponse(
        {
            "logs_by_day": logs_by_day,
            "actions_by_type": actions_by_type,
        }
    )
