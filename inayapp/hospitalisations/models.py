from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.contrib.auth.models import User
import django.utils.timezone

User = get_user_model()


class Room(models.Model):
    """Modèle pour les chambres d'hospitalisation"""
    ROOM_TYPES = [
        ("single", "Chambre individuelle"),
        ("double", "Chambre double"),
        ("triple", "Chambre triple"),
        ("quad", "Chambre quadruple"),
        ("vip", "Chambre VIP"),
        ("soins_intensifs", "Soins Intensifs"),
        ("pediatrie", "Chambre Pédiatrie"),
    ]
    service = models.ForeignKey(
        "medical.Service",
        on_delete=models.PROTECT,
        related_name="rooms",
        verbose_name="Service",
    )
    room_number = models.CharField(
        max_length=10, unique=True, verbose_name="Numéro de chambre"
    )

    floor = models.IntegerField(default=1, verbose_name="Étage")
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPES,
        default="double",
        verbose_name="Type de chambre",
    )
    bed_capacity = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name="Nombre de lits",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    night_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("15000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix par nuitée (DA)",
        help_text="Prix facturé par nuit de séjour",
    )

    maintenance_required = models.BooleanField(
        default=False,
        verbose_name="Maintenance requise",
        help_text="Indique si la chambre nécessite une maintenance",
    )
    room_equipment = models.TextField(
        blank=True,
        null=True,
        verbose_name="Équipements de la chambre",
        help_text="Liste des équipements disponibles dans la chambre",
    )

    special_requirements = models.TextField(
        blank=True,
        null=True,
        verbose_name="Exigences spéciales",
        help_text="Exigences particulières pour cette chambre",
    )

    class Meta:
        ordering = ["service", "floor", "room_number"]
        unique_together = ["service", "room_number"]
        verbose_name = "Chambre"
        verbose_name_plural = "Chambres"

    def __str__(self):
        return f"Chambre {self.room_number} - {self.service.name}"

    @property
    def occupied_beds_count(self):
        """Nombre de lits occupés dans la chambre"""
        return self.beds.filter(is_occupied=True, is_active=True).count()

    @property
    def available_beds_count(self):
        """Nombre de lits disponibles dans la chambre"""
        return self.beds.filter(
            is_occupied=False, maintenance_required=False, is_active=True
        ).count()

    @property
    def occupancy_rate(self):
        """Taux d'occupation de la chambre"""
        if self.bed_capacity == 0:
            return 0
        return round((self.occupied_beds_count / self.bed_capacity) * 100, 1)

    @property
    def is_full(self):
        """Vérifie si la chambre est complète"""
        return self.occupied_beds_count >= self.bed_capacity

    @property
    def monthly_revenue(self):
        """Revenus mensuels de la chambre"""
        from django.utils import timezone
        from datetime import timedelta

        month_start = timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return self.admissions.filter(
            admission_date__gte=month_start, discharge_date__isnull=False
        ).aggregate(total=models.Sum("total_cost"))["total"] or Decimal("0.00")


class Bed(models.Model):
    """Modèle pour les lits"""

    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="beds", verbose_name="Chambre"
    )
    bed_number = models.CharField(max_length=10, verbose_name="Numéro de lit")
    is_occupied = models.BooleanField(default=False, verbose_name="Occupé")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    # NOUVEAUX CHAMPS pour la configuration
    BED_TYPE_CHOICES = [
        ("standard", "Lit Standard"),
        ("electrique", "Lit Électrique"),
        ("isolation", "Lit d'Isolation"),
        ("pediatrique", "Lit Pédiatrique"),
        ("geriatrique", "Lit Gériatrique"),
        ("reanimation", "Lit de Réanimation"),
    ]

    bed_type = models.CharField(
        max_length=20,
        choices=BED_TYPE_CHOICES,
        default="standard",
        verbose_name="Type de lit",
    )

    bed_equipment = models.TextField(
        blank=True,
        null=True,
        verbose_name="Équipements du lit",
        help_text="Équipements spéciaux associés à ce lit",
    )

    equipment_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes sur les équipements",
        help_text="Notes particulières sur les équipements",
    )

    maintenance_required = models.BooleanField(
        default=False,
        verbose_name="Maintenance requise",
        help_text="Indique si le lit nécessite une maintenance",
    )

    special_requirements = models.TextField(
        blank=True,
        null=True,
        verbose_name="Exigences spéciales",
        help_text="Exigences particulières pour ce lit",
    )
    last_cleaned = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernière désinfection"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["room", "bed_number"]
        unique_together = ["room", "bed_number"]
        verbose_name = "Lit"
        verbose_name_plural = "Lits"

    def __str__(self):
        return f"Lit {self.bed_number} - Chambre {self.room.room_number}"

    @property
    def current_patient(self):
        """Patient actuellement dans le lit"""
        if not self.is_occupied:
            return None

        current_admission = self.admissions.filter(
            is_active=True, discharge_date__isnull=True
        ).first()

        return current_admission.patient if current_admission else None

    @property
    def current_admission(self):
        """Admission actuelle du lit"""
        if not self.is_occupied:
            return None

        return self.admissions.filter(
            is_active=True, discharge_date__isnull=True
        ).first()

    @property
    def status_display(self):
        """Affichage du statut du lit"""
        if self.maintenance_required:
            return "Maintenance"
        elif self.is_occupied:
            return "Occupé"
        else:
            return "Disponible"

    @property
    def total_occupancy_days(self):
        """Nombre total de jours d'occupation"""
        return sum(admission.length_of_stay for admission in self.admissions.all())

    def save(self, *args, **kwargs):
        # Auto-nettoyer le lit après une sortie
        if not self.is_occupied and not self.last_cleaned:
            self.last_cleaned = timezone.now()
        super().save(*args, **kwargs)


class AdmissionRequest(models.Model):
    """Demande d'admission en attente"""

    STATUS_CHOICES = [
        ("waiting", "En attente"),
        ("approved", "Approuvé"),
        ("admitted", "Admis"),
        ("cancelled", "Annulé"),
        ("transferred", "Transféré"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="admission_requests",
        verbose_name="Patient",
    )
    service = models.ForeignKey(
        "medical.Service",
        on_delete=models.PROTECT,
        related_name="admission_requests",
        verbose_name="Service demandé",
    )
    referring_doctor = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
        verbose_name="Médecin référent",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="waiting", verbose_name="Statut"
    )

    reason = models.TextField(verbose_name="Motif d'admission")
    diagnosis = models.CharField(
        max_length=255, blank=True, verbose_name="Diagnostic préliminaire"
    )

    request_date = models.DateTimeField(
        default=timezone.now, verbose_name="Date de demande"
    )
    estimated_duration = models.IntegerField(
        null=True, blank=True, verbose_name="Durée estimée (jours)"
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    created_by = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_admission_requests",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        ordering = ["-request_date"]
        verbose_name = "Demande d'admission"
        verbose_name_plural = "Demandes d'admission"

    def __str__(self):
        return f"Demande {self.patient.nom_complet} - {self.service.name}"


class Admission(models.Model):
    """Modèle étendu pour les admissions"""

    DISCHARGE_DESTINATIONS = [
        ("domicile", "Domicile"),
        ("autre_hopital", "Transfert vers autre hôpital"),
        ("clinique", "Clinique spécialisée"),
        ("ehpad", "EHPAD / Maison de retraite"),
        ("centre_readaptation", "Centre de rééducation"),
        ("soins_palliatifs", "Soins palliatifs"),
        ("deces", "Décès"),
        ("autre", "Autre"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="admissions",
        verbose_name="Patient",
    )
    bed = models.ForeignKey(
        Bed, on_delete=models.CASCADE, related_name="admissions", verbose_name="Lit"
    )
    admission_request = models.ForeignKey(
        AdmissionRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions",
        verbose_name="Demande d'admission",
    )
    attending_doctor = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Médecin traitant",
    )
    admission_date = models.DateTimeField(
        default=timezone.now, verbose_name="Date d'admission"
    )
    discharge_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de sortie"
    )

    # Champs pour gérer les séjours par lit
    bed_start_date = models.DateTimeField(
        default=timezone.now, verbose_name="Début dans ce lit"
    )
    bed_end_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Fin dans ce lit"
    )
    is_current_bed = models.BooleanField(default=True, verbose_name="Lit actuel")
    parent_admission = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bed_stays",
        verbose_name="Admission principale",
    )

    diagnosis = models.TextField(verbose_name="Diagnostic")
    treatment_plan = models.TextField(blank=True, verbose_name="Plan de traitement")
    discharge_notes = models.TextField(blank=True, verbose_name="Notes de sortie")
    discharge_destination = models.CharField(
        max_length=30,
        choices=DISCHARGE_DESTINATIONS,
        blank=True,
        verbose_name="Destination de sortie",
    )

    # Coût pour ce séjour spécifique dans ce lit
    bed_stay_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût du séjour dans ce lit",
        null=True,
        blank=True,
    )

    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût total",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    created_by = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-admission_date"]
        verbose_name = "Admission"
        verbose_name_plural = "Admissions"

    def __str__(self):
        return f"Admission {self.patient.last_name} {self.patient.first_name} - {self.admission_date.strftime('%d/%m/%Y')}"

    @property
    def bed_stay_days(self):
        """Durée du séjour dans ce lit en jours"""
        try:
            end_date = self.bed_end_date or timezone.now()
            delta = (end_date.date() - self.bed_start_date.date()).days
            return max(1, delta + 1)  # Au minimum 1 jour
        except Exception:
            return 1

    @property
    def length_of_stay(self):
        """Durée totale du séjour en jours"""
        try:
            # Si c'est une admission principale
            if self.parent_admission is None:
                end_date = self.discharge_date or timezone.now()
                delta = (end_date.date() - self.admission_date.date()).days
                return max(1, delta + 1)
            else:
                # Si c'est un séjour dans un lit spécifique
                return self.bed_stay_days
        except Exception:
            return 1

    @property
    def night_price(self):
        """Prix par nuit de la chambre"""
        try:
            if self.bed and self.bed.room and self.bed.room.night_price:
                return self.bed.room.night_price
            return Decimal("0.00")
        except Exception:
            return Decimal("0.00")

    def calculate_bed_stay_cost(self):
        """Calcule le coût du séjour dans ce lit spécifique"""
        try:
            length = self.bed_stay_days
            price = self.night_price
            return length * price
        except Exception:
            return Decimal("0.00")

    def calculate_total_cost(self):
        """Calcule le coût total du séjour"""
        try:
            # Si c'est une admission principale avec des transferts
            if self.parent_admission is None and self.bed_stays.exists():
                total = self.bed_stay_cost or Decimal("0.00")
                # Ajouter les coûts de tous les séjours dans différents lits
                for stay in self.bed_stays.all():
                    total += stay.bed_stay_cost or Decimal("0.00")
                return total
            else:
                # Si pas de transfert, calculer normalement
                length = self.length_of_stay
                price = self.night_price
                return length * price
        except Exception:
            return Decimal("0.00")

    def get_all_bed_stays(self):
        """Retourne tous les séjours dans différents lits pour cette admission"""
        if self.parent_admission is None:
            # Retourner l'admission principale + tous les séjours
            stays = [self]
            stays.extend(self.bed_stays.all().order_by("bed_start_date"))
            return stays
        else:
            # Si c'est déjà un séjour secondaire, retourner tous les séjours du parent
            return self.parent_admission.get_all_bed_stays()

    def save(self, *args, **kwargs):
        try:
            is_new = self.pk is None

            # VALIDATION: Si c'est un transfert (a un parent_admission),
            # ne pas dupliquer l'admission_request
            if self.parent_admission and self.admission_request:
                self.admission_request = None

            # Si c'est une nouvelle admission
            if is_new:
                # CORRECTION: Créer ou récupérer le dossier médical du patient
                try:
                    dossier_medical, created = (
                        self.patient.dossier_medical.get_or_create(
                            defaults={"patient": self.patient}
                        )
                    )
                except:
                    # Si il n'y a pas de dossier médical, on peut continuer sans erreur
                    pass

                # Mettre à jour le statut de la demande d'admission
                if (
                    self.admission_request
                    and self.admission_request.status == "waiting"
                ):
                    self.admission_request.status = "admitted"
                    self.admission_request.save()

                # Marquer le lit comme occupé
                if self.bed and self.is_active and not self.discharge_date:
                    self.bed.is_occupied = True
                    self.bed.save()

            # Si c'est une sortie (discharge_date vient d'être défini)
            elif self.discharge_date and not self.is_active:
                # Calculer le coût du séjour dans ce lit
                if self.is_current_bed:
                    self.bed_end_date = self.discharge_date
                    self.bed_stay_cost = self.calculate_bed_stay_cost()

                # Calculer le coût total
                self.total_cost = self.calculate_total_cost()

                # Libérer le lit lors de la sortie
                if self.bed and self.is_current_bed:
                    self.bed.is_occupied = False
                    self.bed.last_cleaned = None
                    self.bed.save()

            super().save(*args, **kwargs)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Erreur lors de la sauvegarde de l'admission {self.id}: {str(e)}"
            )
            raise


# Nouveau modèle pour l'historique des séjours
class StayHistory(models.Model):
    """Historique détaillé des séjours pour la traçabilité"""

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="stay_histories",
        verbose_name="Patient",
    )
    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name="stay_details",
        verbose_name="Admission",
    )
    bed = models.ForeignKey(Bed, on_delete=models.CASCADE, verbose_name="Lit")
    start_date = models.DateTimeField(verbose_name="Date début")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="Date fin")
    cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Coût"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Historique de séjour"
        verbose_name_plural = "Historiques de séjour"

    def __str__(self):
        return f"{self.patient.nom_complet} - Lit {self.bed.bed_number} ({self.start_date.strftime('%d/%m/%Y')})"


class TransferHistory(models.Model):
    """Historique des transferts de patients entre lits"""

    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name="Admission",
    )

    from_bed = models.ForeignKey(
        Bed,
        on_delete=models.CASCADE,
        related_name="transfers_from",
        verbose_name="Lit d'origine",
    )
    to_bed = models.ForeignKey(
        Bed,
        on_delete=models.CASCADE,
        related_name="transfers_to",
        verbose_name="Lit de destination",
    )

    transfer_date = models.DateTimeField(
        default=timezone.now, verbose_name="Date de transfert"
    )
    transferred_by = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Transféré par",
    )
    reason = models.TextField(blank=True, verbose_name="Motif du transfert")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        ordering = ["-transfer_date"]
        verbose_name = "Historique de transfert"
        verbose_name_plural = "Historiques de transferts"


    def __str__(self):
        return f"Transfert de {self.admission.patient} le {self.transfer_date.date()}"

    @property
    def cost_difference(self):
        """Différence de coût entre les lits"""
        return self.to_bed.room.night_price - self.from_bed.room.night_price

    def save(self, *args, **kwargs):
        # Libérer l'ancien lit et occuper le nouveau
        if not self.pk:
            self.from_bed.is_occupied = False
            self.from_bed.save()

            self.to_bed.is_occupied = True
            self.to_bed.save()

            # Mettre à jour l'admission avec le nouveau lit
            self.admission.bed = self.to_bed
            self.admission.save()

        super().save(*args, **kwargs)


# hospitalisation/models.py
class Transfer(models.Model):
    """Modèle de transfert simplifié"""

    Transfer_admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name="transfers_admission"
    )
    Transfer_from_bed = models.ForeignKey(
        Bed, on_delete=models.CASCADE, related_name="transfers_from_lit"
    )
    Transfer_to_bed = models.ForeignKey(
        Bed, on_delete=models.CASCADE, related_name="transfers_to_lit"
    )
    transfer_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    created_by = models.ForeignKey(
        "rh.Personnel", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"Transfert #{self.id} - {self.Transfer_admission.patient}"
