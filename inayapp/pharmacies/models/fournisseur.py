# pharmacies/models/fournisseur.py


import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import (MaxValueValidator, MinValueValidator,
                                    RegexValidator)
from django.db import models, transaction
from django.db.models import F
from django.forms import ValidationError
from django.urls import reverse
from django.utils import timezone


class Fournisseur(models.Model):
    TYPE_PAIEMENT_CHOICES = [
        ("VIREMENT", "Virement bancaire"),
        ("CHEQUE", "Chèque"),
        ("ESPECES", "Espèces"),
        ("CREDIT", "Crédit"),
    ]

    STATUT_CHOICES = [
        ("ACTIF", "Actif"),
        ("SUSPENDU", "Suspendu"),
        ("ARCHIVE", "Archivé"),
    ]

    FORMES_JURIDIQUES = [
        ("SARL", "SARL"),
        ("EURL", "EURL"),
        ("SNC", "SNC"),
        ("ETS", "ETS"),
        ("AUTRE", "Autre"),
    ]

    code_fournisseur = models.CharField(
        "Code unique",
        max_length=20,
        unique=True,
        help_text="Identifiant unique du fournisseur",
    )
    raison_sociale = models.CharField("Raison sociale", max_length=255, unique=True)
    forme_juridique = models.CharField(
        max_length=50, choices=FORMES_JURIDIQUES, default="SARL"
    )
    domaine_activite = models.CharField("Domaine d'activité", max_length=100)
    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20)
    adresse = models.TextField()
    ville = models.CharField(max_length=100)
    pays = models.CharField(max_length=100, default="Algérie")
    conditions_paiement = models.PositiveIntegerField(
        "Délai de paiement (jours)",
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(365)],
    )
    limite_credit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    solde = models.DecimalField(
        "Solde actuel", max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    mode_paiement_prefere = models.CharField(
        max_length=50, choices=TYPE_PAIEMENT_CHOICES, default="VIREMENT"
    )
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default="ACTIF")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        constraints = [
            models.UniqueConstraint(
                fields=["code_fournisseur", "raison_sociale"], name="unique_fournisseur"
            )
        ]

    def __str__(self):
        return f"{self.code_fournisseur} - {self.raison_sociale}"

    @property
    def credit_disponible(self):
        return self.limite_credit - self.solde

    def mettre_a_jour_solde(self, montant, operation="ajout"):
        with transaction.atomic():
            if operation == "ajout":
                Fournisseur.objects.filter(pk=self.pk).update(
                    solde=F("solde") + montant
                )
            elif operation == "retrait":
                Fournisseur.objects.filter(pk=self.pk).update(
                    solde=F("solde") - montant
                )
            self.refresh_from_db()

    def clean(self):
        if self.limite_credit < 0:
            raise ValidationError(
                {"limite_credit": "La limite de crédit ne peut pas être négative"}
            )

        if self.conditions_paiement > 365:
            raise ValidationError(
                {"conditions_paiement": "Le délai ne peut excéder 365 jours"}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
