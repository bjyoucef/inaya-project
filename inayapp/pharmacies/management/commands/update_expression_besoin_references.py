# management/commands/update_expression_besoin_references.py

from django.core.management.base import BaseCommand
from django.db import transaction
from pharmacies.models import ExpressionBesoin
from datetime import datetime


class Command(BaseCommand):
    help = "Met à jour les références des expressions de besoin existantes"

    def handle(self, *args, **options):
        with transaction.atomic():
            expressions = ExpressionBesoin.objects.all().order_by("date_creation")

            for expression in expressions:
                # Générer une nouvelle référence basée sur les données existantes
                year = expression.date_creation.year
                month = expression.date_creation.month

                # Code du service
                service_code = (
                    expression.service_demandeur.name[:4].upper().replace(" ", "")
                )

                # Code utilisateur
                if expression.created_by:
                    user_code = (
                        expression.created_by.first_name[:4].upper()
                        if expression.created_by.first_name
                        else expression.created_by.username[:4].upper()
                    )
                else:
                    user_code = "SYS"  # Pour les anciennes données sans créateur

                # Compter les expressions avant celle-ci
                count = (
                    ExpressionBesoin.objects.filter(
                        date_creation__lt=expression.date_creation,
                        date_creation__year=year,
                        service_demandeur=expression.service_demandeur,
                    ).count()
                    + 1
                )

                # Nouvelle référence
                new_reference = f"EB-{year}-{service_code}-{user_code}-{count:03d}"

                # Vérifier l'unicité
                if (
                    ExpressionBesoin.objects.filter(reference=new_reference)
                    .exclude(pk=expression.pk)
                    .exists()
                ):
                    # Si la référence existe déjà, ajouter un suffixe
                    suffix = 1
                    while ExpressionBesoin.objects.filter(
                        reference=f"{new_reference}-{suffix}"
                    ).exists():
                        suffix += 1
                    new_reference = f"{new_reference}-{suffix}"

                expression.reference = new_reference
                expression.save(update_fields=["reference"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Référence mise à jour : {expression.pk} -> {new_reference}"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Toutes les références ont été mises à jour avec succès!"
                )
            )
