# inventaire/management/commands/import_initial_data.py
from django.core.management.base import BaseCommand
from inventaire.models import *


class Command(BaseCommand):
    help = "Import initial data for inventory"

    def handle(self, *args, **options):
        # Créer des catégories par défaut
        categories = [
            ("Équipement médical", "equipement"),
            ("Fournitures médicales", "fourniture"),
            ("Médicaments", "medicament"),
            ("Consommables", "consommable"),
            ("Mobilier", "equipement"),
            ("Informatique", "equipement"),
        ]

        for nom, type_item in categories:
            CategorieItem.objects.get_or_create(
                nom=nom, defaults={"type_item": type_item}
            )

        # Créer des marques par défaut
        marques = [
            "Phillips",
            "Siemens",
            "GE Healthcare",
            "Medtronic",
            "Johnson & Johnson",
            "Pfizer",
            "Roche",
            "Abbott",
        ]

        for marque in marques:
            Marque.objects.get_or_create(nom=marque)

        self.stdout.write(self.style.SUCCESS("Successfully imported initial data"))
