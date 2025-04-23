from django.contrib.auth.models import User
from django.db import models


class RendezVous(models.Model):
    """Modèle amélioré pour la gestion des rendez-vous médicaux"""

    STATUT_CHOICES = [
        ("PLANIFIE", "Planifié"),
        ("CONFIRME", "Confirmé"),
        ("ANNULE", "Annulé"),
        ("TERMINE", "Terminé"),
    ]

    service = models.ForeignKey(
        "medical.Service", on_delete=models.SET_NULL, null=True, related_name="appointments"
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="rendez_vous",
        verbose_name="Patient",
    )

    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="rendez_vous",
        verbose_name="Médecin",
    )

    date_heure = models.DateTimeField(verbose_name="Date et heure du rendez-vous")
    duree = models.PositiveIntegerField(
        default=30, verbose_name="Durée prévue (minutes)"
    )

    motif = models.TextField(verbose_name="Motif de consultation")
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="PLANIFIE",
        verbose_name="Statut du rendez-vous",
    )
    notes = models.TextField(
        blank=True, null=True, verbose_name="Notes supplémentaires"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="rendez_vous_crees",
        verbose_name="Créé par",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Dernière mise à jour"
    )

    class Meta:
        verbose_name = "Rendez-vous Médical"
        verbose_name_plural = "Rendez-vous Médicaux"
        ordering = ["-date_heure"]
        constraints = [
            models.UniqueConstraint(
                fields=["medecin", "date_heure"], name="unique_booking_per_doctor"
            )
        ]

    def __str__(self):
        return f"{self.patient} - {self.medecin} ({self.date_heure})"
