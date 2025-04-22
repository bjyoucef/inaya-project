from django.db import models

from rh.models import Personnel
from django.db import models
from django.utils import timezone

class Patient(models.Model):
    GENDER_CHOICES = [
        ("M", "Masculin"),
        ("F", "Féminin"),
    ]

    SECURITE_SOCIALE_CHOICES = [
        ("1", "CNAS"),
        ("2", "CASNOS"),
    ]

    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    date_of_birth = models.DateField(verbose_name="Date de naissance", blank=True, null=True)
    place_of_birth = models.CharField(max_length=100, verbose_name="Lieu de naissance", blank=True, null=True)
    social_security_number = models.CharField(
        max_length=15, unique=True, verbose_name="Numéro de sécurité sociale", blank=True, null=True
    )
    nom_de_assure = models.CharField(
        max_length=100, verbose_name="Nom de l'assuré", blank=True, null=True
    )
    securite_sociale = models.CharField(
        max_length=1,
        choices=SECURITE_SOCIALE_CHOICES,
        verbose_name="Sécurité sociale",
        blank=True,
        null=True,
    )
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, verbose_name="Genre"
    )
    phone_number = models.CharField(max_length=20, verbose_name="Téléphone", blank=True, null=True)
    email = models.EmailField(blank=True, verbose_name="Email", null=True)
    address = models.TextField(blank=True, verbose_name="Adresse", null=True)
    id_created_par = models.ForeignKey(
        Personnel,
        models.DO_NOTHING,
        db_column="created_par",
        related_name="patients_id_created_par",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False, verbose_name="Créé le")

    id_updated_par = models.ForeignKey(
        Personnel,
        models.DO_NOTHING,
        db_column="id_updated_par",
        related_name="patients_id_updated_par",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    is_active = models.BooleanField(default=True, verbose_name="Actif")    

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"

    def delete(self, using=None, keep_parents=False):
        self.is_active = False
        self.save()
