# Generated by Django 5.1.7 on 2025-07-09 23:09

import django.db.models.deletion
import filer.fields.file
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("filer", "0017_image__transparent"),
    ]

    operations = [
        migrations.CreateModel(
            name="Documents",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nom", models.CharField(max_length=100)),
                (
                    "fichier",
                    filer.fields.file.FilerFileField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="filer.file",
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_document", "Peut visualiser le document"),
                    ("download_document", "Peut télécharger le document"),
                ),
            },
        ),
    ]
