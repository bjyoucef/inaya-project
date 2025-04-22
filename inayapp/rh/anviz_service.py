# rh/anviz_service.py
import json
import re
import time
from datetime import date

import requests
from django.core.exceptions import ObjectDoesNotExist
from django.core.management import CommandError
from .models import AnvizConfiguration, Attendance
from django.db.models import Max


def get_last_attendance_sync_date():
    last_sync = Attendance.objects.aggregate(last_sync=Max("synced_at"))["last_sync"]

    if last_sync is None:
        # Si aucune date de synchronisation n'existe, on retourne une date très ancienne
        return "2024-01-01"
    
    # Formater la date au format attendu par l'API Anviz
    last_sync = last_sync.strftime("%Y-%m-%d")
    # today = (date.today()).strftime("%Y-%m-%d")

    # if last_sync == today:
    #     # Si la date de dernière synchronisation est aujourd'hui, on retourne une date antérieure
    #     last_sync = "2024-01-01"

    return last_sync


class AnvizAPI:
    def __init__(self, config=None):
        # Récupération de la configuration depuis la base de données
        if config is None:
            try:
                configs = AnvizConfiguration.objects.filter(is_active=True)
                if not configs.exists():
                    raise CommandError("❌ Aucune configuration Anviz active trouvée.")
                for config in configs:
                    self.stdout.write(f"🔄 Synchronisation de la pointeuse à {config.ip_address}")
                    api = AnvizAPI(config=config)

                    if not api.login():
                        self.stderr.write(
                            self.style.ERROR(f"❌ Connexion échouée à {config.ip_address}")
                        )
                        continue  # Passe à la suivante

            except ObjectDoesNotExist:
                config = None

        if not config:
            raise ValueError("Aucune configuration Anviz trouvée dans la base de données.")

        self.ip = config.ip_address
        self.username = config.username
        self.password = config.password
        self.session_timeout = config.session_timeout

        self.base_url = f"http://{self.ip}/goform"
        self.session = requests.Session()
        self.session_key = None

    def _get_timestamp(self):
        return str(int(time.time() * 1000))

    def login(self):
        """Authentification via l'endpoint chklogin"""
        try:
            login_url = f"{self.base_url}/chklogin"
            response = self.session.get(
                login_url,
                params={
                    'userid': self.username,
                    'password': self.password
                },
                timeout=5
            )
            response.raise_for_status()
            # Nettoyer la réponse (retirer <html> et </html>)
            raw_text = response.text.replace("<html>", "").replace("</html>", "").strip()
            # Correction des clés non citées
            json_text = re.sub(r'(\w+):', r'"\1":', raw_text)
            data = json.loads(json_text)

            if data.get('code') == 'success':
                self.session_key = data.get('session_key')
                # Ajout des cookies attendus par la pointeuse
                self.session.cookies.set("session_id", self.username, domain=self.ip, path="/")
                self.session.cookies.set("session_key", self.session_key, domain=self.ip, path="/")
                self.session.cookies.set("session_power", "1", domain=self.ip, path="/")
                return True
            else:
                print(f"Échec de la connexion : {data.get('msg', 'Erreur inconnue')}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la connexion : {e}")
            return False
        except ValueError as e:
            print(f"Erreur lors de l'analyse JSON : {e}")
            return False

    def get_users(self, start=0, limit=20):
        """Récupère la liste des utilisateurs depuis l'appareil"""
        if not self.session_key:
            if not self.login():
                return []

        try:
            users_url = f"{self.base_url}/userlist"
            params = {
                'start': start,
                'limit': limit,
                'session_id': self.username,
                'session_key': self.session_key,
                't': self._get_timestamp()
            }
            headers = {
                "Accept": "application/json, text/html, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/advance/index.html"
            }

            response = self.session.get(users_url, params=params, headers=headers, timeout=5)
            response.raise_for_status()

            # Nettoyage de la réponse en retirant les balises HTML
            raw_text = response.text.replace("<html>", "").replace("</html>", "").strip()
            json_text = re.sub(r'(\w+):', r'"\1":', raw_text)
            data = json.loads(json_text)
            return data.get('record', [])
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la récupération des utilisateurs : {e}")
            return []
        except ValueError as e:
            print(f"Erreur d'analyse JSON lors de la récupération des utilisateurs : {e}")
            return []

    def get_attendances(self, start=0, limit=100):
        """Récupère la liste des enregistrements d'attendances depuis l'appareil"""
        if not self.session_key:
            if not self.login():
                return []

        try:

            from_date = (
                get_last_attendance_sync_date()
            )  # Date de dernière synchronisation des enregistrements d'attendance

            today = date.today()  # Date de fin pour la recherche  
            to_date = today.strftime("%Y-%m-%d")

            attendances_url = f"{self.base_url}/searchrecord"
            params = {
                'start': start,
                'limit': limit,
                'from': from_date,
                'to': to_date,
                'session_id': self.username,
                'session_key': self.session_key,
                't': self._get_timestamp()
            }
            headers = {
                "Accept": "application/json, text/html, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/advance/index.html"
            }
            response = self.session.get(attendances_url, params=params, headers=headers, timeout=5)

            response.raise_for_status()

            # Nettoyage de la réponse pour obtenir un JSON valide
            raw_text = response.text.replace("<html>", "").replace("</html>", "").strip()
            json_text = re.sub(r'([{,]\s*)(\w+)\s*:', r'\1"\2":', raw_text)

            data = json.loads(json_text)
            # On suppose que les enregistrements se trouvent dans la clé "record"
            return data.get('record', [])
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la récupération des attendances : {e}")
            return []
        except ValueError as e:
            print(f"Erreur d'analyse JSON lors de la récupération des attendances : {e}")
            return []


# http://192.168.10.250/goform/userlist?start=0&limit=15&session_id=admin&session_key=1636275619&t=1744300074269
# http://192.168.10.250/goform/searchrecord?start=0&limit=15&userid=&from=&to=&order=asc&session_id=admin&session_key=1664087492&t=1744833365331
# http://192.168.10.250/goform/searchrecord?start=0&limit=15&userid=&from=2025-04-01&to=2025-04-30&order=asc&session_id=admin&session_key=1664087492&t=1744833479587
