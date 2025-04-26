from decimal import Decimal
from django.db import migrations, models


def clean_honoraire_medecin(apps, schema_editor):
    PrestationActe = apps.get_model("medical", "PrestationActe")
    for pa in PrestationActe.objects.all():
        # If NULL, set to zero
        if pa.honoraire_medecin is None:
            pa.honoraire_medecin = Decimal("0.00")
        # If too large, clamp to the max your field allows, e.g. 999999.99
        max_allowed = Decimal("999999.99")
        if pa.honoraire_medecin > max_allowed:
            pa.honoraire_medecin = max_allowed
        pa.save(update_fields=["honoraire_medecin"])


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0007_prestation_honoraire_total_and_more"),
    ]

    operations = [
        migrations.RunPython(clean_honoraire_medecin, migrations.RunPython.noop),
    ]
