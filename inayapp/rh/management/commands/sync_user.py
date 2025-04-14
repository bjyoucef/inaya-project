from django.core.management.base import BaseCommand, CommandError
from rh.models import Employee, AnvizConfiguration
from rh.anviz_service import AnvizAPI
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronise les utilisateurs depuis toutes les pointeuses Anviz actives"

    def handle(self, *args, **options):
        configs = AnvizConfiguration.objects.filter(is_active=True)
        if not configs.exists():
            raise CommandError("❌ Aucune configuration active trouvée pour Anviz.")

        total_synced = 0
        total_errors = 0

        for config in configs:
            self.stdout.write(
                self.style.WARNING(
                    f"🔄 Synchronisation des utilisateurs depuis : {config.ip_address}"
                )
            )

            api = AnvizAPI(config=config)
            if not api.login():
                self.stderr.write(
                    self.style.ERROR(
                        f"❌ Échec de connexion à la pointeuse {config.ip_address}"
                    )
                )
                total_errors += 1
                continue

            start = 0
            limit = 15
            synced_this_device = 0

            while True:
                users = api.get_users(start=start, limit=limit)
                if not users:
                    break

                for user in users:
                    try:
                        user_id = int(user["userid"])
                        name = user.get("username", f"Employé #{user_id}")
                        card_number = user.get("cardid", "")

                        Employee.objects.update_or_create(
                            anviz_id=user_id,
                            defaults={"name": name, "card_number": card_number},
                        )
                        synced_this_device += 1
                    except Exception as e:
                        logger.error(f"⚠️ Erreur utilisateur {user.get('userid')}: {e}")
                        continue

                start += limit

            self.stdout.write(
                f"✅ Pointeuse {config.ip_address} : {synced_this_device} utilisateurs synchronisés"
            )
            total_synced += synced_this_device

        self.stdout.write(
            self.style.SUCCESS(
                f"✔️ Synchronisation des utilisateurs terminée : {total_synced} synchronisés, {total_errors} erreurs de connexion."
            )
        )
