# medical.models.prestation_Kt.py
from decimal import Decimal
from django.db.models import F
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.forms import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()

class ActeKt(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    service = models.ForeignKey("Service", on_delete=models.PROTECT, related_name="actes")

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    class Meta:
        verbose_name = "Acte Kt"
        verbose_name_plural = "Actes Kt"
        permissions = (
            ("view_tarifs_acte", "Peut voir les tarifs des actes"),
            ("manage_tarifs_acte", "Peut gérer les tarifs des actes"),
            ("view_produits_acte", "Peut voir les produits associés aux actes"),
        )

class ActeProduit(models.Model):
    acte = models.ForeignKey(
        "ActeKt",
        on_delete=models.CASCADE,
        related_name="produits_defaut",
        verbose_name="ActeKt médical",
    )
    produit = models.ForeignKey(
        "pharmacies.Produit", on_delete=models.PROTECT, verbose_name="Produit associé"
    )
    quantite_defaut = models.PositiveIntegerField(
        default=1, verbose_name="Quantité par défaut"
    )

    class Meta:
        verbose_name = "Produit par défaut pour acte"
        verbose_name_plural = "Produits par défaut pour actes"
        unique_together = ("acte", "produit")

    def __str__(self):
        return f"{self.acte} - {self.produit} ({self.quantite_defaut})"


class Convention(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Convention KT"
        verbose_name_plural = "Conventions KT"
        permissions = (
            ("approve_convention", "Peut approuver une convention"),
            ("reject_convention", "Peut rejeter une convention"),
            ("manage_dossier_convention", "Peut gérer les dossiers de convention"),
            ("view_convention_stats", "Peut voir les statistiques des conventions"),
        )


class TarifActe(models.Model):
    """
    Modèle simplifié : un tarif pour un acte avec ou sans convention
    """
    acte = models.ForeignKey(
        "ActeKt",
        on_delete=models.CASCADE,
        related_name="tarifs"
    )
    convention = models.ForeignKey(
        "Convention",
        on_delete=models.PROTECT,
        related_name="tarifs_acte",
        null=True,
        blank=True,
        help_text="Convention appliquée. Si vide = tarif de base sans convention"
    )
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant de l'acte"
    )
    montant_honoraire_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant d'honoraire de base",
        help_text="Honoraire de base pour cet acte/convention"
    )
    date_effective = models.DateField(default=timezone.now)
    is_default = models.BooleanField(
        default=False,
        help_text="Cocher pour que ce tarif soit celui par défaut"
    )

    class Meta:
        verbose_name = "Tarif d'acte"
        verbose_name_plural = "Tarifs d'actes"
        ordering = ["-is_default", "-date_effective"]
        permissions = (
            ("set_default_tarif", "Peut définir les tarifs par défaut"),
            ("view_all_tarifs", "Peut voir tous les tarifs"),
            ("manage_tarifs_history", "Peut gérer l'historique des tarifs"),
        )
    def __str__(self):
        conv_text = f" - {self.convention.nom}" if self.convention else " (sans convention)"
        return f"{self.acte.code}{conv_text}: {self.montant} DA"

    def clean(self):
        """Validation : un seul tarif par défaut par acte/convention"""
        if self.is_default:
            existing_default = TarifActe.objects.filter(
                acte=self.acte,
                convention=self.convention,
                is_default=True
            ).exclude(pk=self.pk)

            if existing_default.exists():
                conv_name = self.convention.nom if self.convention else "sans convention"
                raise ValidationError(
                    f"Un tarif par défaut existe déjà pour l'acte {self.acte.code} {conv_name}"
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class PrestationKt(models.Model):
    STATUT_CHOICES = [
        ("PLANIFIE", "Planifié"),
        ("REALISE", "Réalisé"),
        ("PAYE", "Payé"),
        ("ANNULE", "Annulé"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name="Patient",
    )
    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name="Médecin traitant",
    )
    actes = models.ManyToManyField(
        "ActeKt",
        through="PrestationActe",
        related_name="prestations",
        verbose_name="Actes médicaux",
    )
    date_prestation = models.DateTimeField(
        default=timezone.now, verbose_name="Date de réalisation"
    )
    statut = models.CharField(
        max_length=25,
        choices=STATUT_CHOICES,
        default="PLANIFIE",
        verbose_name="Statut de la prestation",
    )
    prix_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Coût total",
    )
    prix_supplementaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Frais supplémentaires",
        help_text="Coût supplémentaire pour la prestation (hors actes et consommations)",
    )
    prix_supplementaire_medecin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Part médecin du supplément",
    )

    observations = models.TextField(blank=True, verbose_name="Observations médicales")

    class Meta:
        verbose_name = "PrestationKt médicale"
        verbose_name_plural = "Prestations médicales"
        ordering = ["-date_prestation"]
        indexes = [
            models.Index(fields=["date_prestation"]),
            models.Index(fields=["statut"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["medecin"]),
            models.Index(fields=["statut", "date_prestation"]),
        ]
        permissions = (
            ("planifier_prestationkt", "Peut planifier des prestations"),
            ("realiser_prestationkt", "Peut réaliser des prestations"),
            ("payer_prestationkt", "Peut marquer comme payé les prestations"),
            ("annuler_prestationkt", "Peut annuler des prestations"),
            ("view_all_prestationkt", "Peut voir toutes les prestations"),
            ("export_prestationkt", "Peut exporter les prestations"),
            ("change_status_prestationkt", "Peut changer le statut des prestations"),
            ("generate_bon_paiement", "Peut générer les bons de paiement"),
            ("view_patient_history", "Peut voir l'historique patient"),
            ####
            ("manage_paiements_especes", "Peut gérer les paiements espèces"),
            ("view_paiements_especes", "Peut consulter les paiements espèces"),
            ("encaisser_especes", "Peut encaisser les paiements espèces"),
            ("supprimer_paiements_especes", "Peut supprimer les paiements espèces"),
            ("view_dashboard_especes", "Peut voir le dashboard des paiements espèces"),
        )
    def __str__(self):
        return f"PrestationKt #{self.id} - {self.patient} ({self.date_prestation.date()})"

    @property
    def details_actes(self):
        return "\n".join(
            f"{pa.acte} ({pa.tarif_conventionne}DA)"
            for pa in self.prestationacte_set.all()
        )

    @property
    def dossier_medical(self):
        return self.patient.dossier_medical

    def get_total_avec_supplementaire(self):
        """Retourne le prix total incluant les frais supplémentaires"""
        return self.prix_total + self.prix_supplementaire

    def calculate_total_price(self):
        """Calcule le prix total incluant actes, consommations supplémentaires et frais supplémentaires"""
        total = Decimal("0.00")

        # Prix des actes
        for pa in self.actes_details.all():
            total += pa.tarif_conventionne

            # Prix des consommations supplémentaires uniquement
            for conso in pa.consommations.all():
                quantite_supplementaire = max(
                    0, conso.quantite_reelle - conso.quantite_defaut
                )
                total += quantite_supplementaire * conso.prix_unitaire

        # Ajouter les frais supplémentaires
        total += self.prix_supplementaire

        return total

    def clean(self):
        """Validation des statuts de la prestation"""
        super().clean()

        # Vérifier la cohérence avec les actes si la prestation existe déjà
        if self.pk:
            self._validate_statut_coherence()

    def _validate_statut_coherence(self):
        """Valide la cohérence entre le statut de la prestation et les actes"""
        actes = self.actes_details.all()

        if self.statut == "PAYE":
            # CORRECTION: Vérifier séparément les actes facturables et les paiements espèces

            # 1. Vérifier les actes facturables (avec convention, hors urgence)
            actes_facturables = actes.filter(
                convention__isnull=False,
                convention_accordee=True,
                dossier_convention_complet=True,
            ).exclude(convention__nom__iexact="urgence")

            if actes_facturables.exists():
                actes_non_payes = actes_facturables.filter(
                    statut_facturation__in=["A_FACTURER", "FACTURE"]
                )
                if actes_non_payes.exists():
                    raise ValidationError(
                        "Impossible de marquer la prestation comme 'Payée' car certains actes "
                        "facturables ne sont pas encore payés."
                    )

            # 2. Vérifier les paiements espèces (urgence ou sans convention)
            actes_especes = actes.filter(
                Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
            )

            if actes_especes.exists():
                # Il doit y avoir un paiement espèces complet
                if (
                    not hasattr(self, "paiement_especes")
                    or self.paiement_especes.statut != "COMPLET"
                ):
                    raise ValidationError(
                        "Impossible de marquer la prestation comme 'Payée' car les paiements "
                        "espèces ne sont pas complets."
                    )

        elif self.statut == "REALISE":
            # Si la prestation est réalisée, on peut avoir des actes en cours de facturation
            pass  # Pas de contrainte particulière

        elif self.statut == "PLANIFIE":
            # Si la prestation est planifiée, aucun acte ne devrait être facturé ou payé
            actes_avances = actes.filter(statut_facturation__in=["FACTURE", "PAYE"])
            if actes_avances.exists():
                raise ValidationError(
                    "Impossible de marquer la prestation comme 'Planifiée' car certains actes "
                    "sont déjà facturés ou payés."
                )

    def peut_etre_marquee_payee(self):
        """Vérifie si la prestation peut être marquée comme payée"""
        actes = self.actes_details.all()

        # Vérifier les actes facturables
        actes_facturables = actes.filter(
            convention__isnull=False,
            convention_accordee=True,
            dossier_convention_complet=True,
        ).exclude(convention__nom__iexact="urgence")

        if actes_facturables.exists():
            actes_non_payes = actes_facturables.filter(
                statut_facturation__in=["A_FACTURER", "FACTURE"]
            )
            if actes_non_payes.exists():
                return False

        # Vérifier les paiements espèces
        actes_especes = actes.filter(
            Q(convention__isnull=True) | Q(convention__nom__iexact="urgence")
        )

        if actes_especes.exists():
            if (
                not hasattr(self, "paiement_especes")
                or self.paiement_especes.statut != "COMPLET"
            ):
                return False

        return True

    def marquer_comme_payee_si_possible(self):
        """Marque la prestation comme payée si toutes les conditions sont remplies"""
        if self.peut_etre_marquee_payee() and self.statut != "PAYE":
            self.statut = "PAYE"
            self.save(update_fields=["statut"])
            return True
        return False

    def save(self, *args, **kwargs):
        # Fix timezone issue: ensure date_prestation is timezone-aware
        if self.date_prestation and timezone.is_naive(self.date_prestation):
            self.date_prestation = timezone.make_aware(self.date_prestation)

        self.clean()
        super().save(*args, **kwargs)


class PrestationActe(models.Model):
    prestation = models.ForeignKey(
        "PrestationKt", on_delete=models.CASCADE, related_name="actes_details"
    )
    acte = models.ForeignKey(
        "ActeKt", on_delete=models.PROTECT, related_name="prestations_liees"
    )
    convention = models.ForeignKey(
        "Convention",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestations",
        verbose_name="Convention appliquée",
    )
    tarif_conventionne = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Tarif conventionné"
    )
    convention_accordee = models.BooleanField(
        null=True,
        blank=True,
        default=True,
        verbose_name="Convention accordée",
        help_text="La convention a-t-elle été accordée au patient ?",
    )
    dossier_convention_complet = models.BooleanField(
        default=False,
        verbose_name="Dossier de convention complet",
        help_text="Le dossier administratif de convention est-il complet et valide ?",
    )
    honoraire_medecin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Honoraire médecin",
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("99999999.99")),
        ],
    )
    commentaire = models.TextField(blank=True, verbose_name="Commentaire médical")

    # CHAMPS DE FACTURATION SIMPLIFIÉS
    STATUT_FACTURATION_CHOICES = [
        ("NON_FACTURABLE", "Non facturable"),
        ("A_FACTURER", "À facturer"),
        ("FACTURE", "Facturé"),
        ("PAYE", "Payé"),
        ("REJETE", "Rejeté"),
        ("ANNULE", "Annulé"),
    ]

    statut_facturation = models.CharField(
        max_length=20,
        choices=STATUT_FACTURATION_CHOICES,
        default="NON_FACTURABLE",
        verbose_name="Statut de facturation",
        help_text="Statut du processus de facturation de l'acte",
    )

    date_facturation = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date de facturation",
        help_text="Date d'envoi de la facture à l'assurance",
    )

    date_paiement = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date de paiement",
        help_text="Date de réception du paiement",
    )

    # Suivi des rejets et litiges
    motif_rejet = models.TextField(
        blank=True,
        verbose_name="Motif de rejet",
        help_text="Raison du rejet par l'assurance",
    )

    date_rejet = models.DateField(blank=True, null=True, verbose_name="Date de rejet")

    class Meta:
        verbose_name = "Détail d'acte"
        verbose_name_plural = "Détails des actes"
        indexes = [
            models.Index(fields=["statut_facturation"]),
            models.Index(fields=["date_facturation"]),
            models.Index(fields=["date_paiement"]),
            models.Index(fields=["statut_facturation", "date_facturation"]),
        ]
        permissions = (
            ("facturer_prestationacte", "Peut facturer les actes"),
            ("payer_prestationacte", "Peut marquer comme payé les actes"),
            ("rejeter_prestationacte", "Peut rejeter les actes"),
            ("view_facturation_details", "Peut voir les détails de facturation"),
            ("manage_conventions", "Peut gérer les conventions"),
            ("manage_paiements_especes", "Peut gérer les paiements espèces"),
            ("view_paiements_especes", "Peut consulter les paiements espèces"),
            ("encaisser_especes", "Peut encaisser les paiements espèces"),
            ("supprimer_paiements_especes", "Peut supprimer les paiements espèces"),
        )
    def __str__(self):
        return f"{self.acte} - {self.prestation}"

    def save(self, *args, **kwargs):
        if not self.tarif_conventionne:
            self.tarif_conventionne = self._get_tarif_applicable()

        if not self.honoraire_medecin:
            self._calculate_honoraire_medecin()

        # Si pas de convention, dossier_convention_complet = False
        if not self.convention:
            self.dossier_convention_complet = False

        # MISE À JOUR AUTOMATIQUE DU STATUT DE FACTURATION
        self._update_statut_facturation()

        super().save(*args, **kwargs)

        # Mettre à jour le statut de la prestation si nécessaire
        self._update_prestation_statut()

    def _update_statut_facturation(self):
        """Met à jour automatiquement le statut de facturation"""
        # Si c'est urgence, ne pas gérer la facturation (réglé immédiatement)
        if self.convention and self.convention.nom.lower() == "urgence":
            self.statut_facturation = "NON_FACTURABLE"
            return

        # Si l'acte peut être facturé et n'est pas encore dans le processus
        if (
            self.peut_facturer_convention
            and self.statut_facturation == "NON_FACTURABLE"
        ):
            self.statut_facturation = "A_FACTURER"

        # Si pas de convention ou convention refusée/incomplète
        elif not self.peut_facturer_convention and self.statut_facturation in [
            "A_FACTURER"
        ]:
            self.statut_facturation = "NON_FACTURABLE"

    def _update_prestation_statut(self):
        """Met à jour le statut de la prestation en fonction des actes"""
        prestation = self.prestation
        actes = prestation.actes_details.all()

        # Si tous les actes facturables sont payés, marquer la prestation comme payée
        actes_facturables = actes.filter(
            convention__isnull=False,
            convention_accordee=True,
            dossier_convention_complet=True
        )
        if actes_facturables.exists():
            tous_payes = all(
                acte.statut_facturation == "PAYE"
                for acte in actes_facturables
            )
            if tous_payes and prestation.statut != "PAYE":
                prestation.statut = "PAYE"
                prestation.save(update_fields=['statut'])

    def facturer(self, date_facturation=None):
        """Marque l'acte comme facturé"""
        # Vérifier si c'est urgence
        if self.convention and self.convention.nom.lower() == "urgence":
            raise ValidationError("Les actes d'urgence ne peuvent pas être facturés - ils sont réglés immédiatement")

        if not self.peut_facturer_convention:
            raise ValidationError("Cet acte ne peut pas être facturé en convention")

        if self.statut_facturation not in ["A_FACTURER"]:
            raise ValidationError(
                f"Impossible de facturer un acte avec le statut '{self.get_statut_facturation_display()}'"
            )

        self.statut_facturation = "FACTURE"
        self.date_facturation = date_facturation or timezone.now().date()
        self.save()
        return f"Acte facturé le {self.date_facturation}"

    def marquer_paye(self, date_paiement=None):
        """Marque l'acte comme payé (paiement complet)"""
        if self.statut_facturation not in ["FACTURE"]:
            raise ValidationError(
                f"Impossible de marquer comme payé un acte avec le statut '{self.get_statut_facturation_display()}'"
            )

        self.statut_facturation = "PAYE"
        self.date_paiement = date_paiement or timezone.now().date()
        self.save()
        return f"Acte marqué comme payé le {self.date_paiement}"

    def marquer_rejete(self, motif_rejet, date_rejet=None):
        """Marque l'acte comme rejeté"""
        if self.statut_facturation not in ["FACTURE"]:
            raise ValidationError(
                f"Impossible de rejeter un acte avec le statut '{self.get_statut_facturation_display()}'"
            )

        if not motif_rejet:
            raise ValidationError("Le motif de rejet est obligatoire")

        self.statut_facturation = "REJETE"
        self.motif_rejet = motif_rejet
        self.date_rejet = date_rejet or timezone.now().date()
        self.save()
        return f"Acte marqué comme rejeté le {self.date_rejet}"

    def clean(self):
        """Validation des champs"""
        if self.tarif_conventionne and self.tarif_conventionne < Decimal("0"):
            raise ValidationError("Le tarif ne peut pas être négatif")

        if self.honoraire_medecin and self.honoraire_medecin < Decimal("0"):
            raise ValidationError("L'honoraire médecin ne peut pas être négatif")

        if self.dossier_convention_complet and not self.convention:
            raise ValidationError(
                "Le dossier de convention ne peut pas être marqué comme complet "
                "s'il n'y a pas de convention sélectionnée."
            )

        if self.statut_facturation == "REJETE" and not self.motif_rejet:
            raise ValidationError("Un motif de rejet est requis pour un acte rejeté")

        if self.statut_facturation == "PAYE" and not self.date_paiement:
            self.date_paiement = timezone.now().date()

        if self.statut_facturation == "FACTURE" and not self.date_facturation:
            self.date_facturation = timezone.now().date()

    def _calculate_honoraire_medecin(self):
        """
        Calcul simplifié des honoraires :
        1) Tarif médecin spécifique (HonorairesMedecin)
        2) montant_honoraire_base depuis TarifActe
        """
        # 1️⃣ Tarif médecin spécifique
        honoraire_config = HonorairesMedecin.objects.get_tarif_effectif(
            medecin=self.prestation.medecin,
            acte=self.acte,
            convention=self.convention,
            date_reference=self.prestation.date_prestation,
        )
        if honoraire_config:
            self.honoraire_medecin = honoraire_config.montant
            return

        # 2️⃣ Honoraire de base depuis TarifActe
        tarif_acte = self._get_tarif_acte_obj()
        if tarif_acte and tarif_acte.montant_honoraire_base > Decimal("0"):
            self.honoraire_medecin = tarif_acte.montant_honoraire_base

    def _get_tarif_applicable(self):
        """Récupère le tarif selon la convention ou le tarif de base"""
        tarif_obj = self._get_tarif_acte_obj()
        return tarif_obj.montant if tarif_obj else Decimal("0.00")

    def _get_tarif_acte_obj(self):
        """Récupère l'objet TarifActe approprié"""
        # Recherche avec convention
        if self.convention:
            tarif = TarifActe.objects.filter(
                acte=self.acte,
                convention=self.convention,
                date_effective__lte=self.prestation.date_prestation
            ).order_by("-date_effective").first()

            if tarif:
                return tarif

        # Recherche tarif de base (sans convention)
        tarif = TarifActe.objects.filter(
            acte=self.acte,
            convention__isnull=True,
            date_effective__lte=self.prestation.date_prestation
        ).order_by("-is_default", "-date_effective").first()

        return tarif

    def get_produits_defaut(self):
        """Récupère les produits par défaut avec leur quantité"""
        return self.acte.produits_defaut.all()

    @property
    def convention_status_display(self):
        """Affichage du statut complet de la convention"""
        if not self.convention:
            return "Sans convention"

        status_parts = []

        # Statut d'accord
        if self.convention_accordee is True:
            status_parts.append("Accordée")
        elif self.convention_accordee is False:
            status_parts.append("Refusée")
        else:
            status_parts.append("En attente")

        # Statut du dossier
        if self.dossier_convention_complet:
            status_parts.append("Dossier complet")
        else:
            status_parts.append("Dossier incomplet")

        return f"{self.convention.nom} - {' - '.join(status_parts)}"

    @property
    def peut_facturer_convention(self):
        """Détermine si on peut facturer en convention"""
        # Urgence ne peut pas être facturée (réglée immédiatement)
        if self.convention and self.convention.nom.lower() == "urgence":
            return False

        return (
                self.convention and
                self.convention_accordee is True and
                self.dossier_convention_complet
        )

    @property
    def en_retard_paiement(self):
        """Vérifie si le paiement est en retard (plus de 30 jours)"""
        if self.statut_facturation == "FACTURE" and self.date_facturation:
            delta = timezone.now().date() - self.date_facturation
            return delta.days > 30
        return False

    @property
    def jours_depuis_facturation(self):
        """Retourne le nombre de jours depuis la facturation"""
        if self.date_facturation:
            delta = timezone.now().date() - self.date_facturation
            return delta.days
        return 0


class PrixSupplementaireConfig(models.Model):
    """
    Configuration du pourcentage de prix supplémentaire par médecin.
    """

    medecin = models.OneToOneField(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="prix_supplementaire_config",
        verbose_name="Médecin",
    )
    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Pourcentage supplémentaire (%)",
        help_text="Pourcentage à appliquer sur le prix supplémentaire par médecin.",
    )

    class Meta:
        verbose_name = "Configuration Prix Supplémentaire KT"
        verbose_name_plural = "Configurations Prix Supplémentaires KT"


class HonorairesMedecinManager(models.Manager):
    def get_tarif_effectif(self, medecin, acte, convention, date_reference):
        """Retourne la configuration valide à une date donnée"""
        return (
            self.filter(
                medecin=medecin,
                acte=acte,
                convention=convention,
                date_effective__lte=date_reference,
            )
            .order_by("-date_effective")
            .first()
        )


class HonorairesMedecin(models.Model):
    """Configuration des honoraires par médecin, acte et convention"""

    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.CASCADE,
        related_name="honoraires_configures",
        verbose_name="Médecin",
    )
    acte = models.ForeignKey(
        "ActeKt",
        on_delete=models.CASCADE,
        related_name="honoraires_medecins",
        verbose_name="ActeKt médical",
    )
    convention = models.ForeignKey(
        "Convention",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="honoraires_medecins",
        verbose_name="Convention appliquée",
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Tarif appliqué",
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    date_effective = models.DateField(default=timezone.now, verbose_name="Date d'effet")

    objects = HonorairesMedecinManager()

    class Meta:
        verbose_name = "Config honoraire médecin"
        verbose_name_plural = "Config honoraires médecins"
        unique_together = ("medecin", "acte", "convention")
        ordering = ["-date_effective"]

    def __str__(self):
        convention = f" - {self.convention.nom}" if self.convention else " (base)"
        return f"{self.medecin} - {self.acte.code}{convention} | {self.montant}DA ({self.date_effective})"

    def clean(self):
        """Validation supplémentaire"""
        if self.montant < Decimal("0"):
            raise ValidationError("Le montant ne peut pas être négatif")
