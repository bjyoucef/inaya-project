import datetime
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, getcontext

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.forms import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from medical.models.services import Service
from datetime import timedelta
from decimal import Decimal
from django.db import models
from django.db.models import F, Sum, Value, ExpressionWrapper, DurationField
from django.utils import timezone

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

    # Champs salaire et employé
    salaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
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
    salary_advance_request = models.BooleanField(default=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def get_associated_services(self):
        if hasattr(self, "medecin_profile"):
            return self.medecin_profile.service.all()
        return Service.objects.none()

    @property
    def taux_horaire(self):
        if self.salaire:
            return (self.salaire / Decimal("160")).quantize(
                Decimal("0.01"), rounding=models.ROUND_HALF_UP
            )
        return Decimal("0.00")

    @property
    def identite_complete(self):
        return f"{self.nom_prenom} ({self.poste.label if self.poste else 'Sans poste'})"

    def get_monthly_advances(self, month, year):
        return self.salary_advances.filter(
            status=SalaryAdvanceRequest.RequestStatus.APPROVED,
            payment_date__month=month,
            payment_date__year=year,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def get_available_advance_amount(self):
        """Calcule le montant maximum d'avance disponible (ex: 30% du salaire)"""
        if not self.salaire:
            return Decimal("0.00")

        # Montant maximum autorisé (30% du salaire)
        max_advance = self.salaire * Decimal("0.3")

        # Montant déjà avancé ce mois
        current_month_advances = self.salary_advances.filter(
            status=SalaryAdvanceRequest.RequestStatus.APPROVED,
            payment_date__month=timezone.now().month,
            payment_date__year=timezone.now().year,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        return max(Decimal("0.00"), max_advance - current_month_advances)

    def get_remaining_leave_days(self, leave_type):
        """Calcule les jours de congé restants par type"""
        # Configuration des jours par type de congé
        LEAVE_ALLOWANCES = {
            LeaveRequest.LeaveType.VACATION: 30,  # 30 jours de congé annuel
            LeaveRequest.LeaveType.SICK: 21,  # 21 jours de congé maladie
            LeaveRequest.LeaveType.MATERNITY: 98,  # 14 semaines
            LeaveRequest.LeaveType.PATERNITY: 3,  # 3 jours
        }

        max_days = LEAVE_ALLOWANCES.get(leave_type, 0)
        current_year = timezone.now().year

        # 1) Construire l'expression de durée : (end_date - start_date) + 1 jour
        duration_expr = ExpressionWrapper(
            F("end_date") - F("start_date") + Value(timedelta(days=1)),
            output_field=DurationField(),
        )

        # 2) Faire sum sur cette durée pour les demandes approuvées de cette année
        agg_result = self.leave_requests.filter(
            leave_type=leave_type,
            status=LeaveRequest.RequestStatus.APPROVED,
            start_date__year=current_year,
        ).aggregate(total_duration=Sum(duration_expr))

        total_duration = agg_result["total_duration"] or timedelta(0)

        # 3) Extraire le nombre de jours entiers à partir du timedelta
        used_days = total_duration.days

        # 4) Retourner le nombre de jours restants, jamais négatif
        return max(0, max_days - used_days)

    def __str__(self):
        return f"{self.nom_prenom}"

    class Meta:
        ordering = ["nom_prenom"]
        managed = True
        permissions = [
            ("create_for_others", "Peut créer des demandes pour d'autres employés"),
        ]
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
        verbose_name="Shift associé",
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
    id_acte = models.ForeignKey(
        "HonorairesActe", models.DO_NOTHING, db_column="id_acte", blank=True, null=True
    )
    id_planning = models.ForeignKey(
        "Planning", models.CASCADE, db_column="id_planning", blank=True, null=True
    )
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
    ip_address = models.GenericIPAddressField("Adresse IP", protocol="IPv4")
    username = models.CharField("Nom d'utilisateur", max_length=100)
    password = models.CharField("Mot de passe", max_length=100)
    session_timeout = models.PositiveIntegerField(
        "Délai de session (secondes)", default=1800
    )
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
    shift_type = models.ForeignKey(
        "ShiftType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Type de contrat",
    )
    cycle_start_date = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="Date de début du cycle de rotation"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
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
        return f"{self.employee} à {self.check_time.strftime('%d/%m/%Y %H:%M')}"


class JourFerie(models.Model):
    date = models.DateField(unique=True, verbose_name="Date")
    name = models.CharField(max_length=100, verbose_name="Nom")
    
    @classmethod
    def get_all_dates(cls):
        return set(cls.objects.values_list("date", flat=True))

    class Meta:
        verbose_name = "Jour férié"
        verbose_name_plural = "Jours fériés"

    def __str__(self):
        return f"{self.name} ({self.date})"

def validate_work_days(value):
    if value:
        days = value.split(',')
        valid_days = set(map(str, range(7)))
        if not all(day.strip() in valid_days for day in days):
            raise ValidationError("Jours invalides. Utiliser des chiffres 0-6 séparés par des virgules.")
from datetime import datetime, timedelta
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ShiftType(models.Model):
    FIXED = "fixed"
    ROTATING = "rotating"
    FLEXIBLE = "flexible"
    CUSTOM = "custom"

    SHIFT_CATEGORIES = [
        (FIXED, "Horaires fixes"),
        (ROTATING, "Rotation"),
        (FLEXIBLE, "Horaires flexibles"),
        (CUSTOM, "Personnalisé"),
    ]

    name = models.CharField(max_length=100, verbose_name="Nom du type de contrat")
    category = models.CharField(max_length=20, choices=SHIFT_CATEGORIES, default=FIXED)

    # Champs pour les horaires fixes
    work_days = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Jours travaillés (0-6, séparés par des virgules)",
        help_text="Lundi=0, Dimanche=6. Ex: '0,1,2,3,4' pour Lun-Ven",
    )
    start_time = models.TimeField(null=True, blank=True, verbose_name="Heure de début")
    end_time = models.TimeField(null=True, blank=True, verbose_name="Heure de fin")

    # Champs pour les rotations
    work_days_count = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Jours travaillés par cycle"
    )
    rest_days_count = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Jours de repos par cycle"
    )
    rotation_start_time = models.TimeField(
        null=True, blank=True, verbose_name="Heure de début (rotation)"
    )
    rotation_end_time = models.TimeField(
        null=True, blank=True, verbose_name="Heure de fin (rotation)"
    )

    # Champs pour horaires personnalisés/flexibles
    shift_duration_hours = models.FloatField(
        null=True, blank=True, verbose_name="Durée du shift en heures"
    )
    break_duration_minutes = models.PositiveIntegerField(
        null=True, blank=True, default=0, verbose_name="Durée de pause en minutes"
    )

    # Tolérance pour la classification des pointages
    entry_tolerance_minutes = models.PositiveIntegerField(
        default=120, verbose_name="Tolérance entrée (minutes)"
    )
    exit_tolerance_minutes = models.PositiveIntegerField(
        default=120, verbose_name="Tolérance sortie (minutes)"
    )

    is_night_shift = models.BooleanField(default=False, verbose_name="Poste de nuit")
    crosses_midnight = models.BooleanField(
        default=False, verbose_name="Traverse minuit"
    )

    considers_weekends_holidays = models.BooleanField(
        default=False, verbose_name="Considère les week-ends et jours fériés"
    )

    def get_hours_for_date(self, target_date, employee):
        """
        Retourne les horaires de travail pour une date donnée selon le type de shift.
        Gère tous les types de shifts dynamiquement.
        """
        if self.category == self.FIXED:
            return self._get_fixed_hours(target_date)

        elif self.category == self.ROTATING:
            return self._get_rotating_hours(target_date, employee)

        elif self.category == self.FLEXIBLE:
            return self._get_flexible_hours(target_date, employee)

        elif self.category == self.CUSTOM:
            return self._get_custom_hours(target_date, employee)

        return (None, None)

    def _get_fixed_hours(self, target_date):
        """Gère les horaires fixes"""
        if not self.work_days:
            return (None, None)

        try:
            work_days_set = set(int(day.strip()) for day in self.work_days.split(","))
            weekday = target_date.weekday()

            if weekday in work_days_set:
                return (self.start_time, self.end_time)
        except (ValueError, AttributeError):
            return (None, None)

        return (None, None)
    def get_shift_duration(self):
        """Calcule la durée effective du shift en heures (sans pause)"""
        if self.shift_duration_hours:
            base_duration = self.shift_duration_hours
        else:
            # Calcul automatique basé sur les heures
            start, end = None, None

            if self.category == self.FIXED:
                start, end = self.start_time, self.end_time
            elif self.category == self.ROTATING:
                start, end = self.rotation_start_time, self.rotation_end_time
            else:
                return 8.0  # Durée par défaut

            if start and end:
                start_minutes = start.hour * 60 + start.minute
                end_minutes = end.hour * 60 + end.minute

                if self.is_cross_midnight_shift():
                    # Shift traverse minuit
                    duration_minutes = (24 * 60 - start_minutes) + end_minutes
                else:
                    duration_minutes = end_minutes - start_minutes
                
                base_duration = duration_minutes / 60.0
            else:
                base_duration = 8.0

        # Soustraire la durée de pause
        break_hours = self.break_duration_minutes / 60 if self.break_duration_minutes else 0
        effective_duration = base_duration - break_hours
        
        return max(effective_duration, 0)
    
    def _get_rotating_hours(self, target_date, employee):
        """Gère les rotations dynamiques"""
        if not employee.cycle_start_date:
            cycle_start = employee.created_at.date()
        else:
            cycle_start = (
                employee.cycle_start_date.date()
                if hasattr(employee.cycle_start_date, "date")
                else employee.cycle_start_date
            )

        work_days = self.work_days_count or 0
        rest_days = self.rest_days_count or 0
        total_cycle = work_days + rest_days

        if total_cycle == 0:
            return (None, None)

        days_since_start = (target_date - cycle_start).days
        cycle_day = days_since_start % total_cycle

        if cycle_day < work_days:
            return (self.rotation_start_time, self.rotation_end_time)

        return (None, None)

    def _get_flexible_hours(self, target_date, employee):
        """Gère les horaires flexibles - basé sur les pointages historiques"""
        # Pour les horaires flexibles, on peut utiliser une heure standard
        # ou calculer basé sur l'historique des pointages de l'employé
        if hasattr(employee, "reference_start") and hasattr(employee, "reference_end"):
            if employee.reference_start and employee.reference_end:
                return (employee.reference_start, employee.reference_end)

        # Valeurs par défaut pour horaires flexibles
        default_start = self.start_time or datetime.strptime("08:00", "%H:%M").time()
        default_end = self.end_time or datetime.strptime("17:00", "%H:%M").time()

        return (default_start, default_end)

    def _get_custom_hours(self, target_date, employee):
        """Gère les horaires personnalisés - peut être étendu selon les besoins"""
        # Logique personnalisée selon les règles métier spécifiques
        # Peut inclure des règles complexes basées sur la date, l'employé, etc.

        # Exemple : horaires différents selon le jour de la semaine
        weekday = target_date.weekday()

        # Weekend horaires spéciaux
        if weekday >= 5:  # Samedi/Dimanche
            if self.considers_weekends_holidays:
                # Horaires weekend
                weekend_start = datetime.strptime("10:00", "%H:%M").time()
                weekend_end = datetime.strptime("18:00", "%H:%M").time()
                return (weekend_start, weekend_end)
            else:
                return (None, None)

        # Horaires semaine normaux
        return (self.start_time, self.end_time)

    def is_cross_midnight_shift(self):
        """Détermine si le shift traverse minuit"""
        if self.crosses_midnight:
            return True

        # Auto-détection basée sur les heures
        if self.category == self.FIXED:
            return self.start_time and self.end_time and self.end_time < self.start_time
        elif self.category == self.ROTATING:
            return (
                self.rotation_start_time
                and self.rotation_end_time
                and self.rotation_end_time < self.rotation_start_time
            )

        return self.is_night_shift

    def get_shift_duration(self):
        """Calcule la durée du shift en heures"""
        if self.shift_duration_hours:
            return self.shift_duration_hours

        # Calcul automatique basé sur les heures
        start, end = None, None

        if self.category == self.FIXED:
            start, end = self.start_time, self.end_time
        elif self.category == self.ROTATING:
            start, end = self.rotation_start_time, self.rotation_end_time

        if start and end:
            start_minutes = start.hour * 60 + start.minute
            end_minutes = end.hour * 60 + end.minute

            if self.is_cross_midnight_shift():
                # Shift traverse minuit
                duration_minutes = (24 * 60 - start_minutes) + end_minutes
            else:
                duration_minutes = end_minutes - start_minutes

            return duration_minutes / 60.0

        return 8.0  # Durée par défaut

    def clean(self):
        super().clean()

        if self.category == self.FIXED:
            if not self.work_days:
                raise ValidationError(
                    "Les horaires fixes nécessitent des jours travaillés."
                )
            if not (self.start_time and self.end_time):
                raise ValidationError(
                    "Les horaires fixes nécessitent des heures de début/fin."
                )

        elif self.category == self.ROTATING:
            if not (self.work_days_count and self.rest_days_count):
                raise ValidationError(
                    "Les rotations nécessitent le nombre de jours travaillés/repos."
                )
            if not (self.rotation_start_time and self.rotation_end_time):
                raise ValidationError(
                    "Les rotations nécessitent des heures de début/fin."
                )

        # Validation cohérence heures pour postes de jour
        if not self.is_night_shift and not self.crosses_midnight:
            if self.category == self.FIXED and self.start_time and self.end_time:
                if self.end_time <= self.start_time:
                    raise ValidationError(
                        "L'heure de fin doit être après l'heure de début pour les postes de jour."
                    )
            elif (
                self.category == self.ROTATING
                and self.rotation_start_time
                and self.rotation_end_time
            ):
                if self.rotation_end_time <= self.rotation_start_time:
                    raise ValidationError(
                        "L'heure de fin doit être après l'heure de début pour les postes de jour."
                    )

    def __str__(self):
        return f"{self.get_category_display()} - {self.name}"


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
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvée"
        REJECTED = "REJECTED", "Rejetée"
        CANCELED = "CANCELED", "Annulée"

    personnel = models.ForeignKey(
        "Personnel", on_delete=models.CASCADE, related_name="salary_advances"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    request_date = models.DateField(default=timezone.now)
    payment_date = models.DateField()
    status = models.CharField(
        max_length=8, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reason = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(
        blank=True, null=True, verbose_name="Motif de rejet"
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_salary_advances",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Validation des données avant sauvegarde"""
        super().clean()

        # Vérifier que le montant est positif
        if self.amount <= 0:
            raise ValidationError("Le montant doit être positif")

        # Vérifier que la date de paiement n'est pas dans le passé
        if self.payment_date < timezone.now().date():
            raise ValidationError("La date de paiement ne peut pas être dans le passé")

        # Vérifier le montant disponible
        if self.personnel_id:
            available_amount = self.personnel.get_available_advance_amount()
            if self.amount > available_amount:
                raise ValidationError(
                    f"Montant demandé ({self.amount}) supérieur au montant disponible ({available_amount})"
                )

    def can_be_canceled(self):
        """Vérifie si la demande peut être annulée"""
        return self.status == self.RequestStatus.PENDING

    def can_be_processed(self):
        """Vérifie si la demande peut être traitée"""
        return self.status == self.RequestStatus.PENDING

    def __str__(self):
        return (
            f"Avance {self.amount} pour {self.personnel} - {self.get_status_display()}"
        )

    class Meta:
        permissions = [
            (
                "process_salaryadvance_request",
                "Peut traiter les demandes d'avance sur salaire",
            ),
        ]
        ordering = ["-created_at"]


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        VACATION = "VAC", "Congé annuel"
        SICK = "SIC", "Congé maladie"
        MATERNITY = "MAT", "Congé maternité"
        PATERNITY = "PAT", "Congé paternité"
        OTHER = "AUT", "Autre"

    class RequestStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        CANCELED = "CANCELED", "Annulé"

    personnel = models.ForeignKey(
        "Personnel", on_delete=models.CASCADE, related_name="leave_requests"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(
        max_length=8, choices=LeaveType.choices, default=LeaveType.VACATION
    )
    status = models.CharField(
        max_length=8, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reason = models.TextField()
    rejection_reason = models.TextField(
        blank=True, null=True, verbose_name="Motif de rejet"
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_leave_requests",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration(self):
        """Calcule la durée en jours"""
        return (self.end_date - self.start_date).days + 1

    def clean(self):
        """Validation des données avant sauvegarde"""
        super().clean()

        # Vérifier que la date de fin est après la date de début
        if self.end_date < self.start_date:
            raise ValidationError("La date de fin doit être après la date de début")

        # Vérifier les jours disponibles
        if self.personnel_id and self.leave_type:
            remaining_days = self.personnel.get_remaining_leave_days(self.leave_type)
            if self.duration > remaining_days:
                raise ValidationError(
                    f"Durée demandée ({self.duration} jours) supérieure aux jours disponibles ({remaining_days})"
                )

        # Vérifier les chevauchements avec d'autres congés approuvés
        if self.personnel_id:
            overlapping = LeaveRequest.objects.filter(
                personnel=self.personnel,
                status=self.RequestStatus.APPROVED,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)

            if overlapping.exists():
                raise ValidationError(
                    "Cette période chevauche avec un congé déjà approuvé"
                )

    def can_be_canceled(self):
        """Vérifie si la demande peut être annulée"""
        return self.status == self.RequestStatus.PENDING

    def can_be_processed(self):
        """Vérifie si la demande peut être traitée"""
        return self.status == self.RequestStatus.PENDING

    def __str__(self):
        return (
            f"{self.get_leave_type_display()} {self.personnel} ({self.duration} jours)"
        )

    class Meta:
        permissions = [
            ("process_leave_request", "Peut traiter les demandes de congé"),
        ]
        ordering = ["-created_at"]


# models.py


class DemandeHeuresSupplementaires(models.Model):
    STATUT_CHOICES = [
        ("en_attente", "En attente"),
        ("approuvee", "Approuvée"),
        ("refusee", "Refusée"),
        ("annulee", "Annulée"),
    ]

    MOTIF_CHOICES = [
        ("urgence_medicale", "Urgence médicale"),
        ("absence_collegue", "Absence collègue"),
        ("surcroit_activite", "Surcroît d'activité"),
        ("garde_exceptionnelle", "Garde exceptionnelle"),
        ("autre", "Autre"),
    ]

    # Informations de base
    numero_demande = models.CharField(max_length=20, unique=True, blank=True)

    # Personnel demandeur
    personnel_demandeur = models.ForeignKey(
        "Personnel",
        on_delete=models.CASCADE,
        related_name="demandes_heures_sup",
        verbose_name="Personnel demandeur",
    )

    # Détails de la demande
    date_debut = models.DateTimeField(verbose_name="Date et heure de début")
    date_fin = models.DateTimeField(verbose_name="Date et heure de fin")
    nombre_heures = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Nombre d'heures"
    )
    motif = models.CharField(max_length=20, choices=MOTIF_CHOICES, verbose_name="Motif")
    description = models.TextField(
        blank=True, null=True, verbose_name="Description détaillée"
    )

    # Statut et validation
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="en_attente",
        verbose_name="Statut",
    )

    # Personnel validateur
    personnel_validateur = models.ForeignKey(
        "Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validations_heures_sup",
        verbose_name="Personnel validateur",
    )

    # Dates de validation
    date_validation = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de validation"
    )

    commentaire_validation = models.TextField(
        blank=True, null=True, verbose_name="Commentaire de validation"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_creees",
    )

    def save(self, *args, **kwargs):
        # Générer un numéro de demande automatique
        if not self.numero_demande:
            year = timezone.now().year
            count = (
                DemandeHeuresSupplementaires.objects.filter(
                    created_at__year=year
                ).count()
                + 1
            )
            self.numero_demande = f"HS{year}{count:04d}"

        super().save(*args, **kwargs)

    @property
    def duree_en_heures(self):
        """Calcule automatiquement la durée en heures"""
        if self.date_debut and self.date_fin:
            delta = self.date_fin - self.date_debut
            return Decimal(str(delta.total_seconds() / 3600)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0.00")

    @property
    def peut_etre_modifiee(self):
        """Vérifie si la demande peut encore être modifiée"""
        return self.statut == "en_attente"

    @property
    def est_en_retard(self):
        """Vérifie si la demande est en retard (date de début passée)"""
        return self.date_debut < timezone.now() and self.statut == "en_attente"

    def __str__(self):
        return f"Demande {self.numero_demande} - {self.personnel_demandeur}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande d'heures supplémentaires"
        verbose_name_plural = "Demandes d'heures supplémentaires"
