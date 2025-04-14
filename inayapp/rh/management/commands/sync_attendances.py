# rh/management/commands/sync_attendances.py
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
from rh.models import Employee, Attendance, AnvizConfiguration
from rh.anviz_service import AnvizAPI
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronise les enregistrements d'attendances depuis toutes les pointeuses Anviz actives"

    def handle(self, *args, **options):
        configs = AnvizConfiguration.objects.filter(is_active=True)
        if not configs.exists():
            raise CommandError("❌ Aucune configuration active trouvée pour Anviz.")

        total_synced = 0
        total_errors = 0

        for config in configs:
            self.stdout.write(
                self.style.WARNING(
                    f"🔄 Synchronisation de la pointeuse : {config.ip_address}"
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
                try:
                    attendances = api.get_attendances(start=start, limit=limit)
                    if not attendances:
                        break

                    processed = self.process_batch(attendances)
                    synced_this_device += processed
                    start += limit
                except Exception as e:
                    logger.error(
                        f"❌ Erreur lors de la récupération des enregistrements depuis {config.ip_address} : {e}"
                    )
                    break

            self.stdout.write(
                f"✅ Pointeuse {config.ip_address} : {synced_this_device} enregistrements synchronisés"
            )
            total_synced += synced_this_device

        self.stdout.write(
            self.style.SUCCESS(
                f"✔️ Synchronisation terminée : {total_synced} réussis, {total_errors} erreurs."
            )
        )

    def process_batch(self, attendances):
        count = 0
        for record in attendances:
            try:
                if not all(key in record for key in ("id", "time", "status")):
                    raise ValueError("Champs manquants dans l'enregistrement")

                emp_id = int(record["id"])
                check_time = make_aware(parse_datetime(record["time"]))
                check_type = self.parse_check_type(record["status"])

                employee = self.get_or_create_employee(emp_id, record.get("name"))

                Attendance.objects.update_or_create(
                    employee=employee,
                    check_time=check_time,
                    defaults={"check_type": check_type},
                )
                count += 1
            except Exception as e:
                logger.error(f"⚠️ Erreur enregistrement {record.get('id')}: {str(e)}")
                continue
        return count

    def parse_check_type(self, status):
        status = str(status).upper()
        if status in ["IN", "1", "CHECKIN"]:
            return "IN"
        elif status in ["OUT", "0", "CHECKOUT"]:
            return "OUT"
        return "2"

    def get_or_create_employee(self, emp_id, name):
        try:
            return Employee.objects.get(anviz_id=emp_id)
        except Employee.DoesNotExist:
            return Employee.objects.create(
                anviz_id=emp_id,
                name=name or f"Employé #{emp_id}",
                card_number=str(emp_id),
            )
