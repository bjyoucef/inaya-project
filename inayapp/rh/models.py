import re

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class Services(models.Model):
    id_service = models.AutoField(primary_key=True)
    service_name = models.CharField(max_length=255)
    prix_joure = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    prix_nuit = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    prix_24h = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    salaire = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    color = models.CharField(max_length=7, blank=True, null=True)

    def __str__(self):
        return self.service_name

    def save(self, *args, **kwargs):
        # Sauvegarde d'abord l'objet
        super().save(*args, **kwargs)

        # Génération automatique de la permission
        content_type = ContentType.objects.get_for_model(Services)
        codename = self._generate_codename()
        name = f"Voir le service {self.service_name}"

        # Création ou mise à jour de la permission
        Permission.objects.update_or_create(
            codename=codename, content_type=content_type, defaults={"name": name}
        )

    def delete(self, *args, **kwargs):
        # Suppression de la permission associée
        content_type = ContentType.objects.get_for_model(Services)
        Permission.objects.filter(
            codename=self._generate_codename(), content_type=content_type
        ).delete()
        super().delete(*args, **kwargs)

    def _generate_codename(self):
        # Génère un nom de code valide pour les permissions
        base_name = re.sub(
            r"[^a-zA-Z0-9_]", "", self.service_name.replace(" ", "_")
        ).lower()
        return f"view_service_{base_name}"[:100]

    class Meta:
        managed = True
        db_table = "services"


class Personnel(models.Model):
    id_personnel = models.AutoField(primary_key=True)
    nom_prenom = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=50, blank=True, null=True)
    id_service = models.ForeignKey(
        Services, on_delete=models.CASCADE, related_name="personnels"
    )
    telephone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    statut_activite = models.BooleanField(default=True)
    use_in_planning = models.BooleanField(default=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.nom_prenom}"

    class Meta:
        ordering = ["nom_prenom"]
        managed = True
        db_table = "personnel"


class Planning(models.Model):
    id_service = models.ForeignKey(Services, on_delete=models.DO_NOTHING)
    shift_date = models.DateField()
    employee = models.ForeignKey(Personnel, on_delete=models.DO_NOTHING)
    shift_type = models.CharField(max_length=50)
    id_created_par = models.ForeignKey(
        Personnel,
        on_delete=models.DO_NOTHING,
        db_column="id_created_par",
        related_name="id_created_par",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    prix_acte = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    paiement = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    # Ce champ enregistre qui a fait le pointage
    pointage_id_created_par = models.ForeignKey(
        Personnel,
        on_delete=models.DO_NOTHING,
        db_column="pointage_id_created_par",
        related_name="pointage_id_created_par",
        blank=True,
        null=True,
    )

    pointage_created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "planning"
        permissions = (
            ("acces_aux_plannings", "Accès aux plannings"),
            ("creer_planning", "Créer un planning"),
            ("modifier_planning", "Modifier un planning"),
            ("supprimer_planning", "Supprimer un planning"),
            ("exporter_planning", "Exporter un planning"),
        )


class HonorairesActe(models.Model):
    id_acte = models.AutoField(primary_key=True)
    name_acte = models.CharField(max_length=50, blank=True, null=True)
    prix_acte = models.DecimalField(
        max_digits=10, decimal_places=0, blank=True, null=True
    )
    id_service = models.ForeignKey(Services, models.DO_NOTHING, db_column="id_service")

    class Meta:
        managed = True
        db_table = "honoraires_acte"


# class PointagesActes(models.Model):
#     id_acte = models.ForeignKey(HonorairesActe, models.DO_NOTHING, db_column='id_acte', blank=True, null=True)
#     id_planning = models.ForeignKey(Planning, models.DO_NOTHING, db_column='id_planning', blank=True, null=True)
#     nbr_actes = models.IntegerField()

#     class Meta:
#         managed = True
#         db_table = 'pointages_actes'
# rh/models.py

###################################################################################
class AnvizConfiguration(models.Model):
    name = models.CharField("Nom", max_length=100, blank=True, null=True)
    ip_address = models.GenericIPAddressField("Adresse IP", protocol='IPv4')
    username = models.CharField("Nom d'utilisateur", max_length=100)
    password = models.CharField("Mot de passe", max_length=100)
    session_timeout = models.PositiveIntegerField("Délai de session (secondes)", default=1800)
    is_active = models.BooleanField("Actif", default=True)
    last_modified = models.DateTimeField("Dernière modification", auto_now=True)

    class Meta:
        verbose_name = "Configuration Pointeuse"
        verbose_name_plural = "Configuration Pointeuse"

    def __str__(self):
        return self.name or f"Config {self.ip_address}"


class Employee(models.Model):
    SHIFT_DAY = "day"
    SHIFT_NIGHT = "night"
    SHIFT_24H = "24h"
    SHIFT_CHOICES = [
        (SHIFT_DAY, "Jour"),
        (SHIFT_NIGHT, "Nuit"),
        (SHIFT_24H, "24h"),
    ]

    anviz_id = models.BigIntegerField(unique=True, verbose_name="ID Anviz")
    name = models.CharField(max_length=100, verbose_name="Nom complet")
    card_number = models.CharField(
        max_length=20, null=True, blank=True, verbose_name="Numéro de badge"
    )
    department = models.PositiveSmallIntegerField(default=0, verbose_name="Département")
    group = models.PositiveSmallIntegerField(default=0, verbose_name="Groupe")
    shift = models.CharField(
        max_length=5,
        choices=SHIFT_CHOICES,
        default=SHIFT_DAY,
        verbose_name="Type de shift",
    )
    reference_start = models.TimeField(
        null=True, blank=True, verbose_name="Heure de début de référence"
    )
    reference_end = models.TimeField(
        null=True, blank=True, verbose_name="Heure de fin de référence"
    )
    last_updated = models.DateTimeField(
        auto_now=True, verbose_name="Dernière mise à jour"
    )

    class Meta:
        verbose_name = "Employé"
        verbose_name_plural = "Employés"

    def __str__(self):
        return f"{self.name} (ID: {self.anviz_id})"


class Attendance(models.Model):
    CHECK_TYPE_CHOICES = [
        ("IN", "Entrée"),
        ("OUT", "Sortie"),
        ("2", "Début pause"),
        ("3", "Fin pause"),
        ("4", "Heure supplémentaire"),
        ("5", "Retard"),
        ("6", "Absence"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendances",
        verbose_name="Employé",
    )
    check_time = models.DateTimeField(verbose_name="Heure de pointage")
    check_type = models.CharField(
        max_length=6, choices=CHECK_TYPE_CHOICES, verbose_name="Type de pointage"
    )
    synced_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de synchronisation"
    )

    class Meta:
        unique_together = ["employee", "check_time"]
        verbose_name = "Pointage"
        verbose_name_plural = "Pointages"
        indexes = [
            models.Index(fields=["check_time"]),
            models.Index(fields=["employee", "check_time"]),
        ]

    def __str__(self):
        return f"{self.employee} - {self.get_check_type_display()} à {self.check_time.strftime('%d/%m/%Y %H:%M')}"

    @property
    def check_type_icon(self):
        icons = {
            "IN": "bi-box-arrow-in-right text-success",
            "OUT": "bi-box-arrow-left text-danger",
            "2": "bi-cup-straw text-warning",
            "3": "bi-cup-fill text-primary",
            "4": "bi-alarm text-info",
            "5": "bi-clock-history text-warning",
            "6": "bi-x-circle text-danger",
        }
        return icons.get(self.check_type, "bi-question-circle")


class SalaryAdvanceRequest(models.Model):
    class RequestStatus(models.TextChoices):
        PENDING = "PEN", "En attente"
        APPROVED = "APP", "Approuvée"
        REJECTED = "REJ", "Rejetée"
        CANCELED = "CAN", "Annulée"

    personnel = models.ForeignKey(
        Personnel, on_delete=models.CASCADE, related_name="salary_advances"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    request_date = models.DateField(default=timezone.now)
    payment_date = models.DateField()
    status = models.CharField(
        max_length=3, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Avance {self.amount} pour {self.personnel} - {self.status}"

    class Meta:
        permissions = [
            (
                "process_salaryadvance_request",
                "Peut traiter les demandes d'avance sur salaire",
            ),
        ]


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        VACATION = "VAC", "Congé annuel"
        SICK = "SIC", "Congé maladie"
        MATERNITY = "MAT", "Congé maternité"
        PATERNITY = "PAT", "Congé paternité"
        OTHER = "AUT", "Autre"

    class RequestStatus(models.TextChoices):
        PENDING = "PEN", "En attente"
        APPROVED = "APP", "Approuvé"
        REJECTED = "REJ", "Rejeté"
        CANCELED = "CAN", "Annulé"

    personnel = models.ForeignKey(
        Personnel, on_delete=models.CASCADE, related_name="leave_requests"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(
        max_length=3, choices=LeaveType.choices, default=LeaveType.VACATION
    )
    status = models.CharField(
        max_length=3, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return (
            f"{self.get_leave_type_display()} {self.personnel} ({self.duration} jours)"
        )

    class Meta:
        permissions = [
            ("process_leave_request", "Peut traiter les demandes de congé"),
        ]
