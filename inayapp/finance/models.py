# finance/models.py

from django.db import models
from django.contrib.auth.models import User

from rh.models import Personnel


class Decharges(models.Model):
    id_decharge = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    id_created_par = models.ForeignKey(
        User, models.DO_NOTHING, db_column="id_created_par", blank=True, null=True
    )
    time_export_decharge_pdf = models.DateTimeField(blank=True, null=True)
    id_export_par = models.ForeignKey(
        Personnel,
        models.DO_NOTHING,
        db_column="id_export_par",
        related_name="decharges_id_export_par_set",
        blank=True,
        null=True,
    )
    id_doctor = models.IntegerField(blank=True, null=True)
    id_doctor_kt = models.IntegerField(blank=True, null=True)
    id_employe = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "decharges"


class Payments(models.Model):
    id_payment = models.AutoField(primary_key=True)
    id_decharge = models.ForeignKey(
        Decharges,
        models.DO_NOTHING,
        db_column="id_decharge",
        blank=True,
        null=True,
        default=None,  # Add this explicitly
    )
    payment = models.DecimalField(max_digits=10, decimal_places=2)
    time_payment = models.DateTimeField(blank=True, null=True)
    id_payment_par = models.ForeignKey(
        Personnel,
        models.DO_NOTHING,
        db_column="id_payment_par",
        related_name="decharges_id_payment_par_set",
        blank=True,
        null=True,
    )

    class Meta:
        managed = True
        db_table = "Payments"
