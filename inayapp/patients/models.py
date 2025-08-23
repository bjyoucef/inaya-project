# patient.models
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from hospitalisations.models import Admission, StayHistory, TransferHistory
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import math

User = get_user_model()


class PatientManager(models.Manager):
    """Manager personnalisé pour les patients"""

    def actifs(self):
        """Retourne seulement les patients actifs"""
        return self.filter(is_active=True)

    def avec_admissions_actives(self):
        """Patients ayant des admissions en cours"""
        return self.filter(
            admissions__is_active=True, admissions__discharge_date__isnull=True
        ).distinct()

    def par_groupe_sanguin(self, groupe):
        """Filtre par groupe sanguin"""
        return self.filter(dossier_medical__groupe_sanguin=groupe)


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
    date_of_birth = models.DateField(
        verbose_name="Date de naissance", blank=True, null=True
    )
    place_of_birth = models.CharField(
        max_length=100, verbose_name="Lieu de naissance", blank=True, null=True
    )
    social_security_number = models.CharField(
        max_length=15,
        unique=True,
        verbose_name="Numéro de sécurité sociale",
        blank=True,
        null=True,
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
    phone_number = models.CharField(
        max_length=20, verbose_name="Téléphone", blank=True, null=True
    )
    email = models.EmailField(blank=True, verbose_name="Email", null=True)
    address = models.TextField(blank=True, verbose_name="Adresse", null=True)

    # Champs de traçabilité
    id_created_par = models.ForeignKey(
        "rh.Personnel",
        models.DO_NOTHING,
        db_column="created_par",
        related_name="patients_id_created_par",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now, editable=False, verbose_name="Créé le"
    )
    id_updated_par = models.ForeignKey(
        "rh.Personnel",
        models.DO_NOTHING,
        db_column="id_updated_par",
        related_name="patients_id_updated_par",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    # Manager personnalisé
    objects = PatientManager()


    @property
    def gender_choices(self):
        return self.GENDER_CHOICES
    
    @property
    def nom_complet(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        """Calcule l'âge du patient"""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return (
            today.year
            - self.date_of_birth.year
            - (
                (today.month, today.day)
                < (self.date_of_birth.month, self.date_of_birth.day)
            )
        )

    @property
    def is_currently_hospitalized(self):
        """Vérifie si le patient est actuellement hospitalisé"""
        return self.admissions.filter(
            is_active=True, discharge_date__isnull=True
        ).exists()

    @property
    def current_admission(self):
        """Retourne l'admission actuelle s'il y en a une"""
        return self.admissions.filter(
            is_active=True, discharge_date__isnull=True, is_current_bed=True
        ).first()

    @property
    def total_hospitalizations(self):
        """Nombre total d'hospitalisations"""
        return self.admissions.count()

    @property
    def total_hospitalization_days(self):
        """Nombre total de jours d'hospitalisation"""
        total_days = 0
        for admission in self.admissions.all():
            if admission.discharge_date:
                days = (
                    admission.discharge_date.date() - admission.admission_date.date()
                ).days + 1
            else:
                days = (
                    timezone.now().date() - admission.admission_date.date()
                ).days + 1
            total_days += days
        return total_days

    @property
    def total_medical_costs(self):
        """Coût médical total"""
        return self.admissions.aggregate(total=models.Sum("total_cost"))[
            "total"
        ] or Decimal("0.00")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["social_security_number"]),
            models.Index(fields=["is_active"]),
        ]

    def delete(self, using=None, keep_parents=False):
        """Soft delete - marque comme inactif au lieu de supprimer"""
        self.is_active = False
        self.save()


class DossierMedicalManager(models.Manager):
    """Manager personnalisé pour DossierMedical"""

    def with_patient_stats(self):
        """Récupère les dossiers avec statistiques des patients"""
        return self.select_related("patient").prefetch_related(
            "patient__admissions", "patient__stay_histories"
        )

    def patients_hospitalises(self):
        """Patients actuellement hospitalisés"""
        return self.filter(
            patient__admissions__is_active=True,
            patient__admissions__discharge_date__isnull=True,
        ).distinct()

    def by_blood_group(self, group):
        """Filtre par groupe sanguin"""
        return self.filter(groupe_sanguin=group)

    def incomplete_records(self):
        """Dossiers incomplets (manque poids, taille ou groupe sanguin)"""
        return self.filter(
            models.Q(groupe_sanguin__isnull=True)
            | models.Q(groupe_sanguin="")
            | models.Q(poids__isnull=True)
            | models.Q(taille__isnull=True)
        )


class DossierMedical(models.Model):
    """Modèle amélioré pour le dossier médical"""

    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="dossier_medical",
        verbose_name="Patient associé",
    )

    GROUPE_SANGUIN_CHOICES = [
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
        choices=GROUPE_SANGUIN_CHOICES,
        blank=True,
        null=True,
        verbose_name="Groupe sanguin",
    )

    poids = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Poids (kg)",
        validators=[MinValueValidator(0.1), MaxValueValidator(1000)],
    )

    taille = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Taille (cm)",
        validators=[MinValueValidator(10), MaxValueValidator(300)],
    )

    # Nouveaux champs médicaux
    allergies = models.TextField(
        blank=True,
        verbose_name="Allergies connues",
        help_text="Liste des allergies du patient",
    )

    antecedents_medicaux = models.TextField(
        blank=True,
        verbose_name="Antécédents médicaux",
        help_text="Historique médical important",
    )

    antecedents_chirurgicaux = models.TextField(
        blank=True,
        verbose_name="Antécédents chirurgicaux",
        help_text="Historique des interventions chirurgicales",
    )

    traitements_actuels = models.TextField(
        blank=True,
        verbose_name="Traitements en cours",
        help_text="Médicaments et traitements actuels",
    )

    medecin_traitant = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Médecin traitant",
        related_name="patients_suivis",
    )

    personne_contact_urgence = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Contact d'urgence",
        help_text="Personne à contacter en cas d'urgence",
    )

    telephone_contact_urgence = models.CharField(
        max_length=20, blank=True, verbose_name="Téléphone contact d'urgence"
    )

    # Champs de traçabilité
    created_by = models.ForeignKey(
        "rh.Personnel",
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

    # Manager personnalisé
    objects = DossierMedicalManager()

    @property
    def imc(self):
        """Calcule l'IMC (Indice de Masse Corporelle)"""
        if self.poids and self.taille:
            taille_m = self.taille / 100  # Conversion cm -> m
            return round(self.poids / (taille_m**2), 1)
        return None

    @property
    def imc_category(self):
        """Catégorie IMC"""
        imc = self.imc
        if not imc:
            return None

        if imc < 18.5:
            return "Insuffisance pondérale"
        elif imc < 25:
            return "Normal"
        elif imc < 30:
            return "Surpoids"
        else:
            return "Obésité"

    @property
    def is_complete(self):
        """Vérifie si le dossier médical est complet"""
        return all(
            [
                self.groupe_sanguin,
                self.poids,
                self.taille,
            ]
        )

    @property
    def completion_percentage(self):
        """Pourcentage de complétude du dossier"""
        fields_to_check = [
            self.groupe_sanguin,
            self.poids,
            self.taille,
            self.allergies,
            self.antecedents_medicaux,
            self.medecin_traitant,
            self.personne_contact_urgence,
        ]

        completed_fields = sum(1 for field in fields_to_check if field)
        return round((completed_fields / len(fields_to_check)) * 100)

    def get_full_history(self):
        """Retourne l'historique médical complet du patient"""
        history = {"admissions": [], "transfers": [], "stays": [], "prestations": []}

        # Récupérer toutes les admissions
        admissions = self.patient.admissions.all().order_by("-admission_date")

        for admission in admissions:
            # Récupérer tous les séjours liés à cette admission
            from hospitalisations.models import StayHistory

            stays = StayHistory.objects.filter(admission=admission).order_by(
                "start_date"
            )

            admission_data = {
                "id": admission.id,
                "admission_date": admission.admission_date,
                "discharge_date": admission.discharge_date,
                "total_cost": admission.total_cost,
                "diagnosis": admission.diagnosis,
                "treatment_plan": admission.treatment_plan,
                "stays": [],
                "length_of_stay": admission.length_of_stay,
            }

            for stay in stays:
                stay_data = {
                    "bed": f"{stay.bed.room.room_number}-{stay.bed.bed_number}",
                    "start_date": stay.start_date,
                    "end_date": stay.end_date,
                    "cost": stay.cost,
                    "service": stay.bed.room.service.name,
                }
                admission_data["stays"].append(stay_data)

            history["admissions"].append(admission_data)

        # Récupérer les prestations médicales
        try:
            prestations = self.patient.prestations.all().order_by("-date_prestation")
            for prestation in prestations:
                prestation_data = {
                    "id": prestation.id,
                    "date": prestation.date_prestation,
                    "medecin": (
                        prestation.medecin.nom_complet
                        if prestation.medecin
                        else "Non spécifié"
                    ),
                    "actes": prestation.details_actes,
                    "prix_total": prestation.prix_total,
                    "statut": prestation.get_statut_display(),
                }
                history["prestations"].append(prestation_data)
        except:
            # Si le modèle Prestation n'existe pas encore
            pass

        return history

    def get_recent_admissions(self, limit=5):
        """Récupère les admissions récentes"""
        return self.patient.admissions.order_by("-admission_date")[:limit]

    def get_statistics(self):
        """Calcule les statistiques médicales du patient"""
        admissions = self.patient.admissions.all()

        stats = {
            "total_admissions": admissions.count(),
            "active_admissions": admissions.filter(
                is_active=True, discharge_date__isnull=True
            ).count(),
            "total_days": 0,
            "total_cost": Decimal("0.00"),
            "average_stay": 0,
            "last_admission": None,
            "most_frequent_service": None,
        }

        if not admissions.exists():
            return stats

        # Calculer les totaux
        total_days = 0
        total_cost = Decimal("0.00")
        stay_durations = []
        services = {}

        for admission in admissions:
            # Durée de séjour
            if admission.discharge_date:
                duration = (
                    admission.discharge_date.date() - admission.admission_date.date()
                ).days + 1
            else:
                duration = (
                    timezone.now().date() - admission.admission_date.date()
                ).days + 1

            total_days += duration
            stay_durations.append(duration)

            # Coût
            if admission.total_cost:
                total_cost += admission.total_cost

            # Services les plus fréquents
            service_name = admission.bed.room.service.name
            services[service_name] = services.get(service_name, 0) + 1

        stats["total_days"] = total_days
        stats["total_cost"] = total_cost
        stats["average_stay"] = (
            sum(stay_durations) / len(stay_durations) if stay_durations else 0
        )
        stats["last_admission"] = admissions.first().admission_date
        stats["most_frequent_service"] = (
            max(services, key=services.get) if services else None
        )

        return stats

    def __str__(self):
        return f"Dossier médical de {self.patient.first_name} {self.patient.last_name}"

    class Meta:
        verbose_name = "Dossier Médical"
        verbose_name_plural = "Dossiers Médicaux"
        indexes = [
            models.Index(fields=["groupe_sanguin"]),
            models.Index(fields=["created_at"]),
        ]
