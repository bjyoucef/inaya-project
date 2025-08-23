# medical/migrations/0010_rename_acte_to_actekt.py
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0009_alter_forfaitproduitinclus_options_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Acte",
            new_name="ActeKt",
        ),
    ]
