# finance/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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


class Tarif_Gardes(models.Model):
    poste = models.ForeignKey("rh.Poste", on_delete=models.CASCADE, related_name="tarifs")
    service = models.ForeignKey(
        "medical.Service", on_delete=models.CASCADE, related_name="tarifs"
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
        verbose_name = "Tarif_Gardes"
        verbose_name_plural = "Tarif_Gardes"

    def __str__(self):
        desc = f"{self.poste} / {self.service}"
        if self.shift:
            desc += f" ({self.shift})"
        return desc


class TarifActe(models.Model):
    acte = models.ForeignKey("medical.Acte", on_delete=models.CASCADE, related_name="tarifs")
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_effective = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.acte.code} - {self.montant}"

    class Meta:
        verbose_name = "Tarif de base"
        verbose_name_plural = "Tarifs de base"
        ordering = ["-date_effective"]


class Convention(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    actes = models.ManyToManyField(
        "medical.Acte", through="TarifActeConvention", related_name="conventions"
    )

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Convention"
        verbose_name_plural = "Conventions"


class TarifActeConvention(models.Model):
    convention = models.ForeignKey(
        Convention, on_delete=models.CASCADE, related_name="tarifs"
    )
    acte = models.ForeignKey(
        "medical.Acte", on_delete=models.CASCADE, related_name="tarifs_convention"
    )
    tarif_acte = models.ForeignKey(
        TarifActe, on_delete=models.CASCADE, related_name="tarifs_par_convention"
    )
    date_effective = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ("convention", "acte")
        verbose_name = "Tarif par convention"
        verbose_name_plural = "Tarifs par convention"
        ordering = ["-date_effective"]

    def __str__(self):
        return f"{self.convention.nom} - {self.acte.code}"
