# tests/test_anviz.py
import json
from django.test import TestCase
from rh.anviz_service import AnvizAPI

class AnvizAPITest(TestCase):
    def test_full_flow(self):
        api = AnvizAPI()
        
        # Test login
        self.assertTrue(api.login())
        
        # Test userlist
        users = api.get_users()
        self.assertGreater(len(users), 0)
        print(json.dumps(users, indent=2))