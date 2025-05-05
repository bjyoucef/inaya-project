from datetime import datetime, timezone
import logging
from django.utils.text import slugify
from requests import request

from medical.models.services import Service

logger = logging.getLogger(__name__)


def get_date_range(config):
    """Retourne la plage de dates validée (start_date <= end_date)."""
    start_date, end_date = config.start_date, config.end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date




def services_autorises(user):
    """
    Renvoie un QuerySet de Service que l'utilisateur peut voir,
    en utilisant user.get_all_permissions() et en
    comparant uniquement des strings (pas de listes).
    """
    # 1) Toutes les permissions de l'utilisateur, au format "app_label.codename"
    user_perms = user.get_all_permissions()
    print(user_perms)
    # 2) Construire un mapping codename -> Service
    #    (codename sans le préﬁxe "app_label.")
    slug_to_service = {}
    for service in Service.objects.all():
        slug = slugify(service.name).replace("-", "_")
        codename = f"view_service_{slug}"
        slug_to_service[codename] = service

    # 3) Extraire uniquement la partie codename de chaque permission
    #    et ne garder que celles qui commencent par "view_service_"
    allowed_codenames = {
        perm.split(".", 1)[1]
        for perm in user_perms
        if perm.startswith("medical.view_service_")
    }

    # 4) Garder les services dont le codename est dans allowed_codenames
    permitted_services = [
        slug_to_service[c] for c in allowed_codenames if c in slug_to_service
    ]

    # 5) On renvoie un QuerySet filtré sur ces IDs pour usage en views
    permitted_ids = [s.id for s in permitted_services]
    return Service.objects.filter(id__in=permitted_ids)
