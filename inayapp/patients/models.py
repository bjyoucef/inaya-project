from django.db import models

from rh.models import Personnel
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

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


class DossierMedical(models.Model):
    """Modèle pour gérer le dossier médical complet d'un patient"""

    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="dossier_medical",
        verbose_name="Patient associé",
    )

    GOUPE_SANGUIN_CHOICES = [
        ("A+", "A+"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B-", "B-"),
        ("AB+", "AB+"),
        ("AB-", "AB-"),
        ("O+", "O+"),
        ("O-", "O-"),
    ]

    groupe_sanguin = models.CharField(
        max_length=3,
        choices=GOUPE_SANGUIN_CHOICES,
        blank=True,
        null=True,
        verbose_name="Groupe sanguin",
    )

    poids = models.FloatField(blank=True, null=True, verbose_name="Poids (kg)")

    taille = models.FloatField(blank=True, null=True, verbose_name="Taille (cm)")

    created_by = models.ForeignKey(
        Personnel,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dossiers_crees",
        verbose_name="Créé par",
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )

    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Dernière mise à jour"
    )

    def __str__(self):
        return f"Dossier médical de {self.patient.first_name} {self.patient.last_name}"

    class Meta:
        verbose_name = "Dossier Médical"
        verbose_name_plural = "Dossiers Médicaux"


class Antecedent(models.Model):
    """Modèle pour gérer les antécédents médicaux d'un patient"""

    TYPE_ANTECEDENT_CHOICES = [
        ("MEDICAL", "Antécédent Médical"),
        ("CHIRURGICAL", "Antécédent Chirurgical"),
        ("FAMILIAL", "Antécédent Familial"),
        ("ALLERGIE", "Allergie"),
        ("TRAITEMENT", "Traitement en cours"),
    ]

    dossier = models.ForeignKey(
        DossierMedical,
        on_delete=models.CASCADE,
        related_name="antecedents",
        verbose_name="Dossier associé",
    )

    type_antecedent = models.CharField(
        max_length=20, choices=TYPE_ANTECEDENT_CHOICES, verbose_name="Type d'antécédent"
    )

    description = models.TextField(verbose_name="Description détaillée")

    date_decouverte = models.DateField(
        verbose_name="Date de découverte", blank=True, null=True
    )

    gravite = models.CharField(
        max_length=50,
        choices=[("LEGERE", "Légère"), ("MODEREE", "Modérée"), ("SEVERE", "Sévère")],
        blank=True,
        null=True,
        verbose_name="Gravité",
    )

    commentaire_medecin = models.TextField(
        blank=True, null=True, verbose_name="Commentaire du médecin"
    )

    documents = models.FileField(
        upload_to="antecedents/",
        blank=True,
        null=True,
        verbose_name="Documents associés",
    )

    def __str__(self):
        return f"{self.get_type_antecedent_display()} - {self.date_decouverte}"

    class Meta:
        verbose_name = "Antécédent Médical"
        verbose_name_plural = "Antécédents Médicaux"
        ordering = ["-date_decouverte"]





