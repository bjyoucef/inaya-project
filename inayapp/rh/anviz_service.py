# rh/anviz_service.py
import requests
import time
import re
import json
from django.conf import settings

class AnvizAPI:
    def __init__(self):
        self.base_url = "http://192.168.10.250/goform"
        self.session = requests.Session()
        self.session_key = None  # La clé de session sera stockée ici après login

    def _get_timestamp(self):
        return str(int(time.time() * 1000))

    def login(self):
        """Authentification via l'endpoint chklogin"""
        try:
            login_url = f"{self.base_url}/chklogin"
            print(f"URL de connexion : {login_url}")
            print(f"Paramètres de connexion : {settings.ANVIZ_CONFIG['USERNAME']}, {settings.ANVIZ_CONFIG['PASSWORD']}")
            response = self.session.get(
                login_url,
                params={
                    'userid': settings.ANVIZ_CONFIG['USERNAME'],
                    'password': settings.ANVIZ_CONFIG['PASSWORD']
                },
                timeout=5
            )
            response.raise_for_status()
            # Nettoyer la réponse (retirer <html> et </html>)
            raw_text = response.text.replace("<html>", "").replace("</html>", "").strip()
            # Correction des clés non citées
            json_text = re.sub(r'(\w+):', r'"\1":', raw_text)
            data = json.loads(json_text)
            print(f"Données de la réponse : {data}")
            if data.get('code') == 'success':
                self.session_key = data.get('session_key')
                # Ajouter les cookies attendus par l'appareil
                self.session.cookies.set("session_id", settings.ANVIZ_CONFIG["USERNAME"], domain="192.168.10.250", path="/")
                self.session.cookies.set("session_key", self.session_key, domain="192.168.10.250", path="/")
                self.session.cookies.set("session_power", "1", domain="192.168.10.250", path="/")
                print(f"Connexion réussie, clé de session : {self.session_key}")
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
                'session_id': settings.ANVIZ_CONFIG['USERNAME'],  # par exemple "admin"
                'session_key': self.session_key,
                't': self._get_timestamp()
            }
            headers = {
                "Accept": "application/json, text/html, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/advance/index.html"
            }
            
            response = self.session.get(users_url, params=params, headers=headers, timeout=5)
            print(f"URL des utilisateurs : {users_url}")
            print(f"Paramètres des utilisateurs : {params}")
            print(f"Réponse des utilisateurs : {response.url}")
            print(f"Contenu de la réponse des utilisateurs : {response.text}")
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
            attendances_url = f"{self.base_url}/searchrecord"
            params = {
                'start': start,
                'limit': limit,
                'session_id': settings.ANVIZ_CONFIG['USERNAME'],
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
            print("JSON formaté :", json_text)
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