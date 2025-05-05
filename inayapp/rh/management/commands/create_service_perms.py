# medical/management/commands/create_service_perms.py
# python manage.py create_service_perms

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from medical.models import Service
import re


def make_codename(name):
    base = re.sub(r"[^a-zA-Z0-9_]", "", name.replace(" ", "_")).lower()
    return f"view_service_{base}"[:100]


class Command(BaseCommand):
    help = "Crée les permissions 'view_service_<slug>' pour tous les Service existants"

    def handle(self, *args, **options):
        ct = ContentType.objects.get_for_model(Service)
        created = 0
        for svc in Service.objects.all():
            codename = make_codename(svc.name)
            perm_name = f"Peut voir le service {svc.name}"
            perm, was_created = Permission.objects.get_or_create(
                codename=codename, content_type=ct, defaults={"name": perm_name}
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"✔️  Créée : {perm.codename}"))
        self.stdout.write(
            self.style.SUCCESS(f"\nTerminé. {created} permissions créées.")
        )
