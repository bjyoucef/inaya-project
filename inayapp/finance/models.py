# finance/models.py

from django.db import models
from django.contrib.auth.models import User

from medical.models.services import Services


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
        User, models.DO_NOTHING,
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
        related_name="payments",
        blank=True,
        null=True,
        default=None,  # Add this explicitly
    )
    payment = models.DecimalField(max_digits=10, decimal_places=2)
    time_payment = models.DateTimeField(blank=True, null=True)
    id_payment_par = models.ForeignKey(
        "rh.Personnel",
        models.DO_NOTHING,
        db_column="id_payment_par",
        related_name="decharges_id_payment_par_set",
        blank=True,
        null=True,
    )

    class Meta:
        managed = True
        db_table = "Payments"


class Tarif(models.Model):
    poste = models.ForeignKey("rh.Poste", on_delete=models.CASCADE, related_name="tarifs")
    service = models.ForeignKey(
        Services, on_delete=models.CASCADE, related_name="tarifs"
    )
    shift = models.ForeignKey(
        "rh.Shift", on_delete=models.CASCADE, null=True, blank=True, related_name="tarifs"
    )
    prix = models.DecimalField(
        "Prix (€)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    salaire = models.DecimalField(
        "Salaire (€)", max_digits=12, decimal_places=2, null=True, blank=True
    )

    class Meta:
        unique_together = ("poste", "service", "shift")
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"

    def __str__(self):
        desc = f"{self.poste} / {self.service}"
        if self.shift:
            desc += f" ({self.shift})"
        return desc
