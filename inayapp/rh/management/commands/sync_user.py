# rh/management/commands/sync_user.py
from django.core.management.base import BaseCommand
from rh.models import Employee
from rh.anviz_service import AnvizAPI

class Command(BaseCommand):
    help = 'Synchronise les utilisateurs Anviz sur toutes les pages'

    def handle(self, *args, **options):
        api = AnvizAPI()
        start = 0
        limit = 15
        total_synced = 0

        while True:
            users = api.get_users(start=start, limit=limit)
            if not users:
                break  # Plus d'utilisateurs à synchroniser

            for user in users:
                # Conversion de l'identifiant en entier si nécessaire
                try:
                    user_id = int(user['userid'])
                except ValueError:
                    user_id = None

                Employee.objects.update_or_create(
                    anviz_id=user_id,
                    defaults={
                        'name': user['username'],
                        'card_number': user.get('cardid', '')
                    }
                )
                total_synced += 1

            # Affichage de la page synchronisée
            self.stdout.write(f"Synchronisé {len(users)} utilisateurs de la page démarrant à {start}")
            start += limit  # Passe à la page suivante

        self.stdout.write(f"Synchronisation terminée, total {total_synced} utilisateurs synchronisés")
