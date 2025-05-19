from decimal import ROUND_HALF_UP, Decimal, getcontext

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from medical.models.services import Service


class Personnel(models.Model):
    id_personnel = models.AutoField(primary_key=True)
    nom_prenom = models.CharField(max_length=100, blank=True, null=True)
    service = models.ForeignKey(
        "medical.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personnels",
    )
    poste = models.ForeignKey(
        "Poste",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Poste occupé",
    )
    telephone = models.CharField(max_length=15, blank=True, null=True)

    # ==== CHAMP salaire et employee par la pointeuse ====
    salaire = models.DecimalField(
        max_digits=10,  # nombre total de chiffres (incluant ceux après la virgule)
        decimal_places=2,  # 2 décimales pour les centimes
        null=True,
        blank=True,
        verbose_name="Salaire mensuel",
    )
    employee = models.OneToOneField(
        "Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Fiche Pointeuse",
        related_name="personnel",
    )
    # ==================================

    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    statut_activite = models.BooleanField(default=True)
    use_in_planning = models.BooleanField(default=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def get_associated_services(self):
        if hasattr(self, "medecin_profile"):
            return self.medecin_profile.service.all()
        return Service.objects.none()

    @property
    def taux_horaire(self):
        if self.salaire:
            return (self.salaire / Decimal("160")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0.00")

    @property
    def identite_complete(self):
        return f"{self.nom_prenom} ({self.poste.label if self.poste else 'Sans poste'})"

    def __str__(self):
        return f"{self.nom_prenom}"

    class Meta:
        ordering = ["nom_prenom"]
        managed = True

    def save(self, *args, **kwargs):
        if not self.salaire:
            self.salaire = 0.00
        super().save(*args, **kwargs)


class Planning(models.Model):
    service = models.ForeignKey("medical.Service", on_delete=models.DO_NOTHING)
    id_poste = models.ForeignKey("Poste", on_delete=models.DO_NOTHING)
    shift_date = models.DateField()
    employee = models.ForeignKey("Personnel", on_delete=models.DO_NOTHING)
    shift = models.ForeignKey(
        "Shift", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Shift associé"
    )
    id_created_par = models.ForeignKey(
        Personnel,
        on_delete=models.DO_NOTHING,
        db_column="id_created_par",
        related_name="id_created_par",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    prix = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, default=0
    )
    prix_acte = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, default=0
    )
    paiement = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, default=0
    )

    # Ce champ enregistre qui a fait le pointage
    pointage_id_created_par = models.ForeignKey(
        "Personnel",
        on_delete=models.DO_NOTHING,
        db_column="pointage_id_created_par",
        related_name="pointage_id_created_par",
        blank=True,
        null=True,
    )
    pointage_created_at = models.DateTimeField(blank=True, null=True)
    id_decharge = models.ForeignKey(
        "finance.Decharges",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plannings",
    )

    class Meta:
        managed = True
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
    id_poste = models.ForeignKey(
        "Poste", models.DO_NOTHING, db_column="id_poste", default=1
    )

    def __str__(self):
        return f"{self.name_acte}"

    class Meta:
        managed = True


class PointagesActes(models.Model):
    id_acte = models.ForeignKey("HonorairesActe", models.DO_NOTHING, db_column='id_acte', blank=True, null=True)
    id_planning = models.ForeignKey("Planning", models.CASCADE, db_column='id_planning', blank=True, null=True)
    nbr_actes = models.IntegerField()

    class Meta:
        managed = True


class Poste(models.Model):
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.label

    class Meta:
        verbose_name = "Poste"
        verbose_name_plural = "Postes"


class Shift(models.Model):
    code = models.CharField(max_length=10, unique=True)
    label = models.CharField(max_length=50)
    debut = models.TimeField(null=True, blank=True)
    fin = models.TimeField(null=True, blank=True)

    def __str__(self):
        return self.label

    class Meta:
        verbose_name = "Shift"
        verbose_name_plural = "Shifts"


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
    anviz_id = models.BigIntegerField(unique=True, verbose_name="ID Anviz")
    name = models.CharField(max_length=100, verbose_name="Nom complet")

    reference_start = models.TimeField(
        null=True, blank=True, verbose_name="Heure de début de référence"
    )
    reference_end = models.TimeField(
        null=True, blank=True, verbose_name="Heure de fin de référence"
    )
    last_updated = models.DateTimeField(
        auto_now=True, verbose_name="Dernière mise à jour"
    )

    def horaires_reference(self):
        if self.reference_start and self.reference_end:
            return f"{self.reference_start.strftime('%H:%M')} - {self.reference_end.strftime('%H:%M')}"
        return "Non défini"

    class Meta:
        verbose_name = "Employé (Pointeuse)"
        verbose_name_plural = "Employés (Pointeuse)"

    def __str__(self):
        return f"{self.name} (ID: {self.anviz_id})"


class Pointage(models.Model):
    employee = models.ForeignKey(
        "Employee",
        on_delete=models.CASCADE,
        related_name="attendances",
        verbose_name="Employé",
    )
    check_time = models.DateTimeField(verbose_name="Heure de pointage")

    ov_validated = models.BooleanField(default=False, verbose_name="heures supplimentaires Validé ")
    validation_date = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation")
    validated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Validé par"
    )

    synced_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de synchronisation"
    )
    def toggle_validation(self, user):
        self.ov_validated = not self.ov_validated
        if self.ov_validated:
            self.validation_date = timezone.now()
            self.validated_by = user
        else:
            self.validation_date = None
            self.validated_by = None
        self.save()
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

class JourFerie(models.Model):
    date = models.DateField(unique=True, verbose_name="Date")
    name = models.CharField(max_length=100, verbose_name="Nom")

    class Meta:
        verbose_name = "Jour férié"
        verbose_name_plural = "Jours fériés"

    def __str__(self):
        return f"{self.name} ({self.date})"


class GlobalSalaryConfig(models.Model):
    # Paramètres CNAS
    cnas_employer_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Taux CNAS employeur (%)",
        default=26.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    cnas_employee_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Taux CNAS employé (%)",
        default=9.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # Indemnités
    daily_meal_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Indemnité repas journalière (DZA)",
        default=300.00,
    )

    daily_transport_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Indemnité transport journalière (DZA)",
        default=200.00,
    )
    overtime_hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.20,
        verbose_name="Taux horaire heures supplémentaires",
    )
    holiday_hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.20,
        verbose_name="Taux horaire heures holiday",
    )
    daily_absence_penalty = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.00,
        verbose_name="Pénalité absence journalière",
    )
    late_minute_penalty = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.00,
        verbose_name="Pénalité par minute de retard",
    )
    # Paramètres généraux
    update_date = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Dernière modification par",
    )

    class Meta:
        verbose_name = "Configuration Salariale Globale"
        verbose_name_plural = "Configuration Salariale Globale"

    def __str__(self):
        return f"Configuration globale - {self.update_date.strftime('%d/%m/%Y')}"

    @classmethod
    def get_latest_config(cls):
        """Récupère la dernière configuration en vigueur"""
        try:
            return cls.objects.latest("update_date")
        except cls.DoesNotExist:
            # Retourne une configuration par défaut si aucune existe
            return cls(
                cnas_employer_rate=Decimal("26.00"),
                cnas_employee_rate=Decimal("9.00"),
                daily_meal_allowance=Decimal("300.00"),
                daily_transport_allowance=Decimal("200.00"),
            )


class IRGBracket(models.Model):
    config = models.ForeignKey(
        GlobalSalaryConfig, on_delete=models.CASCADE, related_name="irg_brackets"
    )
    min_amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Montant minimum"
    )
    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant maximum",
        null=True,
        blank=True,
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Taux d'imposition (%)",
    )

    class Meta:
        ordering = ["min_amount"]
        verbose_name = "Tranche IRG"
        verbose_name_plural = "Tranches IRG"

    def clean(self):
        if self.max_amount and self.min_amount >= self.max_amount:
            raise ValidationError("Le montant maximum doit être supérieur au minimum")

    def __str__(self):
        return f"{self.min_amount} - {self.max_amount or '∞'} : {self.tax_rate}%"


#  ###################################################################################
#  ###################################################################################
#  ###################################################################################
#  ###################################################################################
#  ###################################################################################
class SalaryAdvanceRequest(models.Model):
    class RequestStatus(models.TextChoices):
        PENDING = "PEN", "En attente"
        APPROVED = "APP", "Approuvée"
        REJECTED = "REJ", "Rejetée"
        CANCELED = "CAN", "Annulée"

    personnel = models.ForeignKey(
        "Personnel", on_delete=models.CASCADE, related_name="salary_advances"
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
        "Personnel", on_delete=models.CASCADE, related_name="leave_requests"
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
