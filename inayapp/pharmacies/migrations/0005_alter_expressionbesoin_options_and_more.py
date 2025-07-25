# Generated by Django 5.1.7 on 2025-07-12 19:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0003_service_est_actif"),
        ("pharmacies", "0004_alter_commandefournisseur_besoin_demandeinterne_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="expressionbesoin",
            options={
                "verbose_name": "Expression de besoin",
                "verbose_name_plural": "Expressions de besoin",
            },
        ),
        migrations.AlterField(
            model_name="expressionbesoin",
            name="reference",
            field=models.CharField(blank=True, max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name="expressionbesoin",
            name="service_approvisionneur",
            field=models.ForeignKey(
                blank=True,
                help_text="Service qui traite la demande (pharmacie pour externe, pharmacie pour interne)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="besoins_recus",
                to="medical.service",
            ),
        ),
    ]
