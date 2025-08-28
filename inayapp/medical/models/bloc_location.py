# medical/models/bloc_location.py
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Q


class Bloc(models.Model):
    """Modèle pour les blocs opératoires"""

    nom_bloc = models.CharField(max_length=100, verbose_name="Nom du bloc")
    prix_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix de base (90 min)",
        help_text="Prix pour les 90 premières minutes",
    )
    prix_supplement_30min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("5000.00"),
        verbose_name="Prix par tranche de 30 min supplémentaire",
    )
    est_active = models.BooleanField(default=True, verbose_name="Bloc actif")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        verbose_name = "Bloc opératoire"
        verbose_name_plural = "Blocs opératoires"

    def __str__(self):
        return self.nom_bloc

    def calculer_prix_location(self, duree_minutes):
        """Calcule le prix de location selon la durée"""
        if duree_minutes <= 90:
            return self.prix_base

        # Calcul des tranches supplémentaires de 30 minutes
        minutes_supplementaires = duree_minutes - 90
        tranches_supplementaires = (
            minutes_supplementaires + 29
        ) // 30  # Arrondi au supérieur

        return self.prix_base + (tranches_supplementaires * self.prix_supplement_30min)


class BlocProduitInclus(models.Model):
    """Produits inclus dans la tranche de base de 90 minutes du bloc"""

    bloc = models.ForeignKey(
        Bloc,
        on_delete=models.CASCADE,
        related_name="produits_inclus",
        verbose_name="Bloc",
    )
    produit = models.ForeignKey(
        "pharmacies.Produit", on_delete=models.CASCADE, verbose_name="Produit inclus"
    )
    quantite = models.PositiveIntegerField(default=1, verbose_name="Quantité incluse")

    class Meta:
        verbose_name = "Produit inclus dans le bloc"
        verbose_name_plural = "Produits inclus dans les blocs"
        unique_together = [["bloc", "produit"]]

    def __str__(self):
        return f"{self.bloc.nom_bloc} - {self.produit.nom} ({self.quantite})"


class Forfait(models.Model):
    """Modèle pour les forfaits d'actes"""

    nom = models.CharField(max_length=100, verbose_name="Nom du forfait")
    description = models.TextField(blank=True, verbose_name="Description")
    prix = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix du forfait",
        help_text="Prix total du forfait",
    )
    duree = models.PositiveIntegerField(
        verbose_name="Durée du forfait (en minutes)",
        help_text="Durée totale couverte par le forfait",
    )
    est_active = models.BooleanField(default=True, verbose_name="Forfait actif")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Forfait"
        verbose_name_plural = "Forfaits"

    def __str__(self):
        return self.nom


class ForfaitProduitInclus(models.Model):
    """Modèle pour les produits associés à un forfait"""

    forfait = models.ForeignKey(
        Forfait,
        on_delete=models.CASCADE,
        related_name="produits",
        verbose_name="Forfait associé",
    )
    produit = models.ForeignKey(
        "pharmacies.Produit",
        on_delete=models.CASCADE,
        related_name="forfaits",
        verbose_name="Produit associé",
    )
    quantite = models.PositiveIntegerField(default=1, verbose_name="Quantité")

    class Meta:
        verbose_name = "Produit inclus dans le forfait"
        verbose_name_plural = "Produits inclus dans les forfaits"
        unique_together = [["forfait", "produit"]]

    def __str__(self):
        return f"{self.forfait.nom} - {self.produit.nom} ({self.quantite})"


class ForfaitActeInclus(models.Model):
    """Modèle pour les actes inclus dans un forfait"""

    forfait = models.ForeignKey(
        Forfait,
        on_delete=models.CASCADE,
        related_name="actes_inclus",
        verbose_name="Forfait",
    )
    acte = models.ForeignKey(
        "ActeLocation",
        on_delete=models.CASCADE,
        related_name="forfaits_incluant",
        verbose_name="Acte inclus",
    )
    quantite = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantité incluse",
        help_text="Nombre de fois que cet acte est inclus dans le forfait",
    )
    prix_unitaire_inclus = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire inclus",
        help_text="Prix unitaire de l'acte tel qu'inclus dans le forfait (peut différer du prix standard)",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Acte inclus dans le forfait"
        verbose_name_plural = "Actes inclus dans les forfaits"
        unique_together = [["forfait", "acte"]]

    def __str__(self):
        return f"{self.forfait.nom} - {self.acte.nom} ({self.quantite})"

    def save(self, *args, **kwargs):
        """Si prix_unitaire_inclus n'est pas défini, utiliser le prix standard de l'acte"""
        if self.prix_unitaire_inclus is None:
            self.prix_unitaire_inclus = self.acte.prix
        super().save(*args, **kwargs)

    @property
    def prix_total_inclus(self):
        """Prix total pour cette quantité d'actes inclus"""
        return (self.prix_unitaire_inclus or Decimal("0")) * self.quantite


class ActeLocation(models.Model):
    """Modèle pour les actes pouvant être utilisés dans la location de bloc opératoire"""

    nom = models.CharField(
        max_length=255,
        verbose_name="Nom de l'acte",
        help_text="Nom de l'acte chirurgical ou interventionnel",
    )
    prix = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix de l'acte",
        help_text="Prix de base de l'acte sans les suppléments",
    )
    duree_estimee = models.PositiveIntegerField(
        verbose_name="Durée estimée (minutes)",
        help_text="Durée estimée pour cet acte",
        blank=True,
        null=True,
    )
    est_active = models.BooleanField(default=True, verbose_name="Acte actif")
    description = models.TextField(blank=True, verbose_name="Description de l'acte")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acte de location"
        verbose_name_plural = "Actes de location"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class ActeProduitInclus(models.Model):
    """Produits obligatoires inclus dans un acte"""

    acte = models.ForeignKey(
        ActeLocation,
        on_delete=models.CASCADE,
        related_name="produits_inclus",
        verbose_name="Acte",
    )
    produit = models.ForeignKey(
        "pharmacies.Produit", on_delete=models.CASCADE, verbose_name="Produit inclus"
    )
    quantite_standard = models.PositiveIntegerField(
        default=1, verbose_name="Quantité standard"
    )
    est_obligatoire = models.BooleanField(
        default=True, verbose_name="Produit obligatoire"
    )

    class Meta:
        verbose_name = "Produit inclus dans l'acte"
        verbose_name_plural = "Produits inclus dans les actes"
        unique_together = [["acte", "produit"]]

    def __str__(self):
        return f"{self.acte.nom} - {self.produit.nom} ({self.quantite_standard})"


class LocationBlocActe(models.Model):
    """Association entre LocationBloc et ActeLocation"""

    location = models.ForeignKey(
        "LocationBloc", on_delete=models.CASCADE, related_name="actes_location"
    )
    acte = models.ForeignKey(
        "ActeLocation", on_delete=models.PROTECT, related_name="locations"
    )
    quantite = models.PositiveIntegerField(default=1)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    prix_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Acte dans une location de bloc"
        verbose_name_plural = "Actes dans les locations de bloc"

    def save(self, *args, **kwargs):
        self.prix_total = self.prix_unitaire * self.quantite
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.location} - {self.acte.nom} x{self.quantite}"


class LocationBloc(models.Model):
    """Modèle pour les locations de bloc opératoire - INDÉPENDANT des prestations"""

    TYPE_TARIFICATION_CHOICES = [
        ("FORFAIT", "Forfaitaire"),
        ("DUREE", "À la durée"),
    ]
    STATUT_PAIEMENT_CHOICES = [
        ("EQUILIBRE", "Équilibré"),
        ("SURPLUS_CLINIQUE", "Surplus à verser au médecin"),
        ("COMPLEMENT_MEDECIN", "Complément dû par le médecin"),
        ("AUCUN_PAIEMENT", "Aucun paiement enregistré"),
    ]

    # Informations principales
    bloc = models.ForeignKey(
        "Bloc",
        on_delete=models.PROTECT,
        related_name="locations",
        verbose_name="Bloc opératoire",
    )

    # Informations patient/médecin directement ici
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="locations_bloc",
        verbose_name="Patient",
    )
    medecin = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.PROTECT,
        related_name="locations_bloc",
        verbose_name="Médecin responsable",
    )

    # Informations sur la location
    date_operation = models.DateField(
        verbose_name="Date de l'opération",
        db_index=True,
    )

    heure_operation = models.TimeField(
        verbose_name="Heure de l'opération",
        blank=True,
        null=True,
    )

    # Informations sur l'acte
    nom_acte = models.CharField(
        max_length=255,
        verbose_name="Nom de l'acte chirurgical",
        blank=True,
        null=True,
    )

    # Tarification
    type_tarification = models.CharField(
        max_length=10,
        choices=TYPE_TARIFICATION_CHOICES,
        default="DUREE",
        verbose_name="Type de tarification",
    )
    forfait = models.ForeignKey(
        "Forfait",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="locations",
        verbose_name="Forfait appliqué",
    )

    duree_reelle = models.PositiveIntegerField(
        verbose_name="Durée réelle (minutes)",
        validators=[MinValueValidator(1)],
        blank=True,
        null=True,
        help_text="Durée réelle de l'opération",
    )

    # Prix
    prix_final = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Prix final",
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    prix_supplement_duree = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Supplément durée",
        help_text="Supplément ajouté si la durée réelle dépasse celle du forfait",
    )

    observations = models.TextField(
        blank=True,
        verbose_name="Observations",
    )

    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    date_modification = models.DateTimeField(auto_now=True)

    # Qui a créé/modifié
    cree_par = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="locations_bloc_creees",
        verbose_name="Créé par",
    )

    # CHAMPS POUR LA GESTION DES PAIEMENTS (sans économies)
    montant_paye_caisse = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant payé à la caisse",
        help_text="Montant effectivement reçu par la caisse",
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    difference_paiement = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Différence de paiement",
        help_text="Différence entre montant facturé et montant payé (+ = surplus, - = complément)",
    )

    statut_paiement = models.CharField(
        max_length=20,
        choices=STATUT_PAIEMENT_CHOICES,
        default="AUCUN_PAIEMENT",
        verbose_name="Statut du paiement",
    )

    surplus_a_verser = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Surplus à verser au médecin",
        help_text="Montant que la clinique doit verser au médecin",
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    complement_du_medecin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Complément dû par le médecin",
        help_text="Montant que le médecin doit payer à la clinique",
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    notes_paiement = models.TextField(
        blank=True,
        verbose_name="Notes sur le paiement",
        help_text="Notes relatives au paiement ou aux arrangements financiers",
    )

    date_reglement_surplus = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de règlement du surplus",
        help_text="Date à laquelle le surplus a été versé au médecin",
    )

    date_reglement_complement = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de règlement du complément",
        help_text="Date à laquelle le médecin a payé le complément",
    )
    class Meta:
        verbose_name = "Location de bloc"
        verbose_name_plural = "Locations de bloc"

        # Index composites pour optimiser les requêtes fréquentes
        indexes = [
            models.Index(fields=["bloc", "date_operation"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["medecin"]),
            models.Index(fields=["date_operation"]),
        ]

    def __str__(self):
        return f"{self.bloc.nom_bloc} - {self.patient} - {self.date_operation}"



    def calculer_paiements(self, montant_paye=None):
        """
        Calcule les surplus/compléments basés sur le montant payé
        """
        if montant_paye is None:
            montant_paye = self.montant_paye_caisse

        # Si l'objet n'a pas de PK, on ne peut pas calculer le montant total
        if not self.pk:
            montant_total = self.prix_final or Decimal("0.00")
        else:
            montant_total = self.montant_total_facture

        difference = montant_paye - montant_total

        # Réinitialiser les valeurs
        self.difference_paiement = difference
        self.surplus_a_verser = Decimal("0.00")
        self.complement_du_medecin = Decimal("0.00")

        if montant_paye == 0:
            self.statut_paiement = "AUCUN_PAIEMENT"
        elif difference > 0:
            # Le patient a payé plus que nécessaire
            self.statut_paiement = "SURPLUS_CLINIQUE"
            self.surplus_a_verser = difference
        elif difference < 0:
            # Le patient a payé moins que nécessaire
            self.statut_paiement = "COMPLEMENT_MEDECIN"
            self.complement_du_medecin = abs(difference)
        else:
            # Paiement équilibré
            self.statut_paiement = "EQUILIBRE"

    def save(self, *args, **kwargs):
        """Override save pour calculer automatiquement le prix final et les paiements"""

        # Si l'objet n'a pas encore de PK, faire un premier save pour l'obtenir
        if not self.pk:
            # Save initial sans calculs pour obtenir la PK
            super().save(*args, **kwargs)

        # Maintenant on peut faire les calculs qui nécessitent la PK
        if self.duree_reelle:
            self.prix_final = self.calculer_prix_automatique(self.duree_reelle)
            if self.type_tarification == "FORFAIT":
                self.prix_supplement_duree = self.calculer_supplement_forfait(
                    self.duree_reelle
                )
            else:
                self.prix_supplement_duree = Decimal("0.00")

        # Calcul automatique des paiements (seulement si on a une PK)
        if self.pk:
            self.calculer_paiements()

        # Save final avec tous les calculs
        super().save(*args, **kwargs)

    @property
    def besoin_reglement_surplus(self):
        """Indique si un surplus doit être versé au médecin"""
        return (
            self.statut_paiement == "SURPLUS_CLINIQUE"
            and self.surplus_a_verser > 0
            and not self.date_reglement_surplus
        )

    @property
    def besoin_reglement_complement(self):
        """Indique si un complément est attendu du médecin"""
        return (
            self.statut_paiement == "COMPLEMENT_MEDECIN"
            and self.complement_du_medecin > 0
            and not self.date_reglement_complement
        )

    @property
    def is_reglement_complet(self):
        """Indique si tous les règlements sont effectués"""
        if self.statut_paiement in ["EQUILIBRE", "AUCUN_PAIEMENT"]:
            return True
        elif self.statut_paiement == "SURPLUS_CLINIQUE":
            return bool(self.date_reglement_surplus)
        elif self.statut_paiement == "COMPLEMENT_MEDECIN":
            return bool(self.date_reglement_complement)
        return False

    def get_detail_paiement(self):
        """Retourne un résumé détaillé du statut de paiement"""
        return {
            "montant_facture": self.montant_total_facture,
            "montant_paye": self.montant_paye_caisse,
            "difference": self.difference_paiement,
            "statut": self.get_statut_paiement_display(),
            "surplus_a_verser": self.surplus_a_verser,
            "complement_du_medecin": self.complement_du_medecin,
            "besoin_reglement_surplus": self.besoin_reglement_surplus,
            "besoin_reglement_complement": self.besoin_reglement_complement,
            "is_reglement_complet": self.is_reglement_complet,
            "date_reglement_surplus": self.date_reglement_surplus,
            "date_reglement_complement": self.date_reglement_complement,
            "notes": self.notes_paiement,
        }

    @property
    def duree_effective(self):
        """Retourne la durée appropriée selon le contexte"""
        return self.duree_reelle

    @property
    def montant_total_actes(self):
        """Calcule le montant total des actes supplémentaires"""
        if not self.pk:
            return Decimal("0")
        return sum(acte.prix_total for acte in self.actes_location.all())

    @property
    def montant_total_produits_inclus(self):
        """Montant total des produits inclus (partie incluse seulement)"""
        return sum(c.prix_inclus for c in self.consommations_produits.all())

    @property
    def montant_supplements_produits(self):
        """Montant total des suppléments de produits (uniquement les surplus)"""
        if not self.pk:
            return Decimal("0")
        return sum(c.prix_facturable for c in self.consommations_produits.all())

    @property
    def montant_total_produits_supplementaires(self):
        """Montant des produits supplémentaires uniquement"""
        if not self.pk:
            return Decimal("0")
        return sum(
            c.prix_total
            for c in self.consommations_produits.filter(source_inclusion="SUPPLEMENTAIRE")
        )

    @property
    def montant_total_facture(self):
        """Calcule le montant total de la facture (SANS déduction d'économies)"""
        total = self.prix_final or Decimal("0.00")

        # Vérifier que l'objet a une PK avant d'accéder aux relations
        if not self.pk:
            return total

        # Ajouter les actes supplémentaires (hors forfait ou en tarification à la durée)
        if self.type_tarification == "DUREE":
            # En tarification à la durée, tous les actes sont facturables
            total += self.montant_total_actes
        else:
            # En tarification forfaitaire, seuls les surplus d'actes sont facturables
            total += self.montant_supplements_actes_forfait

        # Ajouter les suppléments de produits et produits supplémentaires
        total += self.montant_supplements_produits
        total += self.montant_total_produits_supplementaires

        return total

    def get_resume_consommation(self):
        """Retourne un résumé détaillé de la consommation (sans économies)"""
        consommations = self.consommations_produits.select_related("produit", "acte_associe")

        resume = {
            "bloc": [],
            "forfait": [],
            "actes": {},
            "supplementaires": [],
            "totaux": {
                "prix_bloc": self.prix_final,
                "prix_actes": self.montant_total_actes,
                "supplements_produits": self.montant_supplements_produits,
                "produits_supplementaires": self.montant_total_produits_supplementaires,
                "total_general": self.montant_total_facture,
            },
        }

        for c in consommations:
            data = {
                "produit": c.produit.nom,
                "quantite_incluse": c.quantite_incluse,
                "quantite_consommee": c.quantite,
                "ecart": c.ecart_quantite,
                "prix_unitaire": c.prix_unitaire,
                "prix_supplement": c.prix_supplement if c.ecart_quantite > 0 else Decimal("0"),
                "est_supplement": c.ecart_quantite > 0,
            }

            if c.source_inclusion == "BLOC":
                resume["bloc"].append(data)
            elif c.source_inclusion == "FORFAIT":
                resume["forfait"].append(data)
            elif c.source_inclusion in ["ACTE", "ACTE_SUPPLEMENTAIRE"]:
                acte_nom = c.acte_associe.acte.nom if c.acte_associe else "Acte inconnu"
                if acte_nom not in resume["actes"]:
                    resume["actes"][acte_nom] = []
                resume["actes"][acte_nom].append(data)
            elif c.source_inclusion == "SUPPLEMENTAIRE":
                data["prix_total"] = c.prix_total
                resume["supplementaires"].append(data)

        return resume

    def calculer_prix_forfait(self, duree_minutes=None):
        """Calcule le prix basé sur le forfait avec supplément éventuel"""
        if not self.forfait:
            return Decimal("0.00")

        prix_base = self.forfait.prix
        duree = duree_minutes or self.duree_effective

        if not duree:
            raise ValueError(
                "Une durée (prévue ou réelle) est nécessaire pour le calcul du prix forfait"
            )

        # Calculer le supplément si la durée dépasse celle du forfait
        if duree > self.forfait.duree:
            minutes_supplementaires = duree - self.forfait.duree
            tranches_supplementaires = (minutes_supplementaires + 29) // 30
            supplement = tranches_supplementaires * self.bloc.prix_supplement_30min
            return prix_base + supplement

        return prix_base

    def calculer_prix_duree(self, duree_minutes=None):
        """Calcule le prix basé sur la durée"""
        duree = duree_minutes or self.duree_effective
        if duree and self.bloc:
            return self.bloc.calculer_prix_location(duree)
        return Decimal("0.00")

    def calculer_prix_automatique(self, duree_minutes=None):
        """Calcule le prix selon le type de tarification"""
        if self.type_tarification == "FORFAIT":
            return self.calculer_prix_forfait(duree_minutes)
        else:
            return self.calculer_prix_duree(duree_minutes)

    def calculer_supplement_forfait(self, duree_minutes=None):
        """Calcule uniquement le supplément pour un forfait"""
        if not self.forfait:
            return Decimal("0.00")

        duree = duree_minutes or self.duree_effective
        if not duree:
            return Decimal("0.00")

        if duree <= self.forfait.duree:
            return Decimal("0.00")

        minutes_supplementaires = duree - self.forfait.duree
        tranches_supplementaires = (minutes_supplementaires + 29) // 30
        return tranches_supplementaires * self.bloc.prix_supplement_30min

    def clean(self):
        """Validation des données"""
        super().clean()

        # Vérifier la cohérence du forfait
        if self.type_tarification == "FORFAIT" and not self.forfait:
            raise ValidationError(
                "Un forfait doit être sélectionné pour la tarification forfaitaire"
            )

    def get_detail_calcul_prix(self):
        """Retourne les détails du calcul de prix avec tous les éléments facturables"""
        duree_utilisee = self.duree_effective
        detail = {
            "prix_bloc": self.prix_final or Decimal("0.00"),
            "montant_actes": self.montant_total_actes,
            "montant_produits_supplementaires": self.montant_total_produits_supplementaires,
            "montant_total": self.montant_total_facture,
        }

        if self.type_tarification == "FORFAIT" and self.forfait:
            detail.update(
                {
                    "type": "forfait",
                    "forfait_nom": self.forfait.nom,
                    "prix_forfait": self.forfait.prix,
                    "duree_incluse": self.forfait.duree,
                    "duree_utilisee": duree_utilisee,
                }
            )

            # Ajouter les détails du supplément si applicable
            if duree_utilisee and duree_utilisee > self.forfait.duree:
                minutes_supp = duree_utilisee - self.forfait.duree
                tranches_supp = (minutes_supp + 29) // 30

                detail.update(
                    {
                        "minutes_supplementaires": minutes_supp,
                        "tranches_supplementaires": tranches_supp,
                        "prix_supplement_30min": self.bloc.prix_supplement_30min,
                        "prix_supplement_total": self.prix_supplement_duree,
                        "avec_supplement": True,
                    }
                )
            else:
                detail["avec_supplement"] = False

        elif self.type_tarification == "DUREE" and duree_utilisee:
            prix_base = self.bloc.prix_base
            detail.update(
                {
                    "type": "duree",
                    "duree_utilisee": duree_utilisee,
                    "prix_base": prix_base,
                    "duree_base": 90,
                    "prix_supplement_30min": self.bloc.prix_supplement_30min,
                }
            )

            if duree_utilisee > 90:
                minutes_supp = duree_utilisee - 90
                tranches_supp = (minutes_supp + 29) // 30
                prix_supp = tranches_supp * self.bloc.prix_supplement_30min

                detail.update(
                    {
                        "minutes_supplementaires": minutes_supp,
                        "tranches_supplementaires": tranches_supp,
                        "prix_supplement_total": prix_supp,
                    }
                )

        return detail
    # Méthodes à ajouter ou modifier dans le modèle LocationBloc

    def get_actes_inclus_forfait(self):
        """Retourne les actes inclus dans le forfait appliqué"""
        if not self.forfait:
            return []

        return self.forfait.actes_inclus.select_related("acte").all()

    def get_ecarts_actes_forfait(self):
        """Calcule les écarts entre actes inclus dans le forfait et actes réellement utilisés"""
        if not self.forfait:
            return []

        actes_inclus = {ai.acte_id: ai for ai in self.get_actes_inclus_forfait()}

        actes_utilises = {}
        for acte_location in self.actes_location.all():
            acte_id = acte_location.acte_id
            if acte_id in actes_utilises:
                actes_utilises[acte_id]["quantite"] += acte_location.quantite
                actes_utilises[acte_id]["prix_total"] += acte_location.prix_total
            else:
                actes_utilises[acte_id] = {
                    "acte": acte_location.acte,
                    "quantite": acte_location.quantite,
                    "prix_unitaire": acte_location.prix_unitaire,
                    "prix_total": acte_location.prix_total,
                }

        ecarts = []

        # Vérifier les actes inclus dans le forfait
        for acte_id, acte_inclus in actes_inclus.items():
            utilise = actes_utilises.get(
                acte_id,
                {
                    "acte": acte_inclus.acte,
                    "quantite": 0,
                    "prix_unitaire": acte_inclus.prix_unitaire_inclus,
                    "prix_total": Decimal("0"),
                },
            )

            ecart_quantite = utilise["quantite"] - acte_inclus.quantite

            ecarts.append(
                {
                    "acte": acte_inclus.acte,
                    "quantite_incluse": acte_inclus.quantite,
                    "quantite_utilisee": utilise["quantite"],
                    "ecart_quantite": ecart_quantite,
                    "prix_unitaire_inclus": acte_inclus.prix_unitaire_inclus,
                    "prix_unitaire_utilise": utilise["prix_unitaire"],
                    "est_supplement": ecart_quantite > 0,
                    "prix_ecart": (
                        ecart_quantite * utilise["prix_unitaire"]
                        if ecart_quantite > 0
                        else Decimal("0")
                    ),
                }
            )

        # Ajouter les actes supplémentaires (non inclus dans le forfait)
        for acte_id, utilise in actes_utilises.items():
            if acte_id not in actes_inclus:
                ecarts.append(
                    {
                        "acte": utilise["acte"],
                        "quantite_incluse": 0,
                        "quantite_utilisee": utilise["quantite"],
                        "ecart_quantite": utilise["quantite"],
                        "prix_unitaire_inclus": Decimal("0"),
                        "prix_unitaire_utilise": utilise["prix_unitaire"],
                        "est_supplement": True,
                        "prix_ecart": utilise["prix_total"],
                    }
                )

        return ecarts

    @property
    def montant_supplements_actes_forfait(self):
        """Montant total des suppléments d'actes par rapport au forfait"""
        if self.type_tarification != "FORFAIT" or not self.pk:
            return Decimal("0")

        total = Decimal("0")
        for ecart in self.get_ecarts_actes_forfait():
            if ecart["est_supplement"]:
                total += ecart["prix_ecart"]

        return total


class ConsommationProduitBloc(models.Model):
    """
    Représente la consommation d'un produit lors d'une location de bloc.
    Gère les quantités incluses, utilisées et les écarts avec calculs automatiques.
    """

    SOURCE_INCLUSION_CHOICES = [
        ('BLOC', 'Inclus dans le bloc'),
        ('FORFAIT', 'Inclus dans le forfait'),
        ('FORFAIT_ACTE', 'Inclus via acte forfaitaire'),
        ('FORFAIT_MIXTE', 'Forfait + acte forfaitaire'),
        ('ACTE', 'Inclus dans un acte'),
        ('ACTE_SUPPLEMENTAIRE', 'Acte supplémentaire'),
        ('SUPPLEMENTAIRE', 'Produit supplémentaire'),
        ('MIXTE', 'Sources multiples'),
    ]

    # Relations
    location = models.ForeignKey(
        'LocationBloc',
        on_delete=models.CASCADE,
        related_name='consommations_produits',
        help_text="Location de bloc associée"
    )

    produit = models.ForeignKey(
        'pharmacies.Produit',
        on_delete=models.CASCADE,
        help_text="Produit consommé"
    )

    acte_associe = models.ForeignKey(
        'LocationBlocActe',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Acte associé si le produit provient d'un acte"
    )

    # CORRECTION: Tous les champs de quantité en DecimalField
    quantite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Quantité réellement utilisée"
    )

    quantite_incluse = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Quantité incluse dans le forfait/bloc/acte"
    )

    ecart_quantite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Écart entre quantité utilisée et incluse (calculé automatiquement)"
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Prix unitaire du produit au moment de la consommation"
    )

    # Statuts et source
    est_inclus = models.BooleanField(
        default=False,
        help_text="True si entièrement inclus (pas de supplément à facturer)"
    )

    source_inclusion = models.CharField(
        max_length=20,
        choices=SOURCE_INCLUSION_CHOICES,
        default='SUPPLEMENTAIRE',
        help_text="Source d'inclusion du produit"
    )

    # Métadonnées
    date_consommation = models.DateTimeField(
        auto_now_add=True,
        help_text="Date et heure de création de l'enregistrement"
    )

    notes = models.TextField(
        blank=True,
        help_text="Notes sur la consommation"
    )

    class Meta:
        db_table = 'medical_consommation_produit_bloc'
        verbose_name = 'Consommation de produit'
        verbose_name_plural = 'Consommations de produits'
        ordering = ['location', 'produit__nom']

        # Contrainte d'unicité pour éviter les doublons
        unique_together = [
            ['location', 'produit', 'acte_associe', 'source_inclusion']
        ]

    def __str__(self):
        return f"{self.produit.nom} - {self.quantite} ({self.location})"

    def save(self, *args, **kwargs):
        """
        Calcule automatiquement l'écart et le statut d'inclusion lors de la sauvegarde.
        """
        # S'assurer que les quantités sont en Decimal
        if not isinstance(self.quantite, Decimal):
            self.quantite = Decimal(str(self.quantite))
        if not isinstance(self.quantite_incluse, Decimal):
            self.quantite_incluse = Decimal(str(self.quantite_incluse))

        # Calcul de l'écart
        self.ecart_quantite = self.quantite - self.quantite_incluse

        # Détermination du statut d'inclusion
        self.est_inclus = (self.ecart_quantite <= 0)

        super().save(*args, **kwargs)


    @property
    def prix_total(self):
        """Alias pour prix_total_utilise - compatible avec l'admin"""
        return self.prix_total_utilise

    @property
    def prix_supplement(self):
        """Prix du supplément (si écart positif)"""
        if self.ecart_quantite > 0:
            return self.ecart_quantite * self.prix_unitaire
        return Decimal("0")


    @property
    def prix_facturable(self):
        """Montant facturable (uniquement les suppléments positifs)"""
        return self.prix_supplement

    @property
    def prix_total_utilise(self):
        """Prix total pour la quantité utilisée."""
        return self.quantite * self.prix_unitaire

    def get_impact_financier(self):
        """
        Retourne un dictionnaire avec les détails de l'impact financier.
        """
        return {
            'quantite_utilisee': float(self.quantite),
            'quantite_incluse': float(self.quantite_incluse),
            'ecart_quantite': float(self.ecart_quantite),
            'prix_unitaire': float(self.prix_unitaire),
            'prix_total_utilise': float(self.prix_total_utilise),
            'montant_supplement': float(self.prix_supplement),
            'est_inclus': self.est_inclus,
            'source_inclusion': self.source_inclusion,
            'source_inclusion_display': self.get_source_inclusion_display(),
        }

    def consolider_avec(self, autre_consommation):
        """
        Consolide cette consommation avec une autre pour le même produit.
        Utilisé pour fusionner les produits provenant de sources multiples.
        """
        if self.produit != autre_consommation.produit:
            raise ValueError("Impossible de consolider des produits différents")

        # Prendre la quantité maximale utilisée
        self.quantite = max(self.quantite, autre_consommation.quantite)

        # Additionner les quantités incluses
        self.quantite_incluse += autre_consommation.quantite_incluse

        # Mettre à jour la source
        if self.source_inclusion != autre_consommation.source_inclusion:
            if 'FORFAIT' in self.source_inclusion and 'FORFAIT' in autre_consommation.source_inclusion:
                self.source_inclusion = 'FORFAIT_MIXTE'
            else:
                self.source_inclusion = 'MIXTE'

        # Recalculer automatiquement lors de la sauvegarde
        self.save()

    @classmethod
    def get_consommations_par_source(cls, location):
        """
        Retourne les consommations groupées par source d'inclusion pour une location.
        """
        consommations = cls.objects.filter(location=location).select_related('produit', 'acte_associe')

        grouped = {}
        for source, _ in cls.SOURCE_INCLUSION_CHOICES:
            grouped[source] = consommations.filter(source_inclusion=source)
        return grouped

    @classmethod
    def calculer_totaux_par_location(cls, location):
        """
        Calcule les totaux financiers pour une location donnée.
        """
        consommations = cls.objects.filter(location=location)

        totaux = {
            'total_utilise': Decimal('0'),
            'total_supplements': Decimal('0'),
            'nombre_produits': consommations.count(),
            'par_source': {}
        }

        for consommation in consommations:
            totaux['total_utilise'] += consommation.prix_total_utilise
            totaux['total_supplements'] += consommation.prix_supplement
            # Totaux par source
            source = consommation.source_inclusion
            if source not in totaux['par_source']:
                totaux['par_source'][source] = {
                    'count': 0,
                    'total_utilise': Decimal('0'),
                    'supplements': Decimal('0')
                }

            totaux['par_source'][source]['count'] += 1
            totaux['par_source'][source]['total_utilise'] += consommation.prix_total_utilise
            totaux['par_source'][source]['supplements'] += consommation.prix_supplement
        return totaux


# Ajout de méthodes dans le modèle LocationBloc pour gérer les nouvelles fonctionnalités

class LocationBlocManager(models.Manager):
    """Manager personnalisé pour LocationBloc avec méthodes utilitaires."""

    def avec_details_complets(self):
        """Retourne un QuerySet avec tous les détails préchargés."""
        return self.select_related(
            'bloc', 'patient', 'medecin', 'forfait', 'cree_par'
        ).prefetch_related(
            'actes_location__acte',
            'consommations_produits__produit',
            'consommations_produits__acte_associe__acte'
        )

    def forfaitaires(self):
        """Retourne uniquement les locations forfaitaires."""
        return self.filter(type_tarification='FORFAIT')

    def a_la_duree(self):
        """Retourne uniquement les locations à la durée."""
        return self.filter(type_tarification='DUREE')

    def avec_ecarts_produits(self):
        """Retourne les locations ayant des écarts de produits."""
        return self.filter(
            consommations_produits__ecart_quantite__ne=0
        ).distinct()


def get_detail_consommations_par_source(self):
    """
    Retourne un dictionnaire détaillé des consommations par source.
    """
    consommations = ConsommationProduitBloc.get_consommations_par_source(self)

    detail = {}
    for source, queryset in consommations.items():
        if queryset.exists():
            detail[source] = {
                'consommations': list(queryset),
                'total_utilise': sum(c.prix_total_utilise for c in queryset),
                'total_supplements': sum(c.prix_supplement for c in queryset),
                'count': queryset.count()
            }

    return detail


def get_ecarts_actes_forfait(self):
    """Calcule les écarts entre actes inclus dans le forfait et actes réellement utilisés"""
    if not self.forfait:
        return []

    actes_inclus = {ai.acte_id: ai for ai in self.get_actes_inclus_forfait()}

    actes_utilises = {}
    for acte_location in self.actes_location.all():
        acte_id = acte_location.acte_id
        if acte_id in actes_utilises:
            actes_utilises[acte_id]["quantite"] += acte_location.quantite
            actes_utilises[acte_id]["prix_total"] += acte_location.prix_total
        else:
            actes_utilises[acte_id] = {
                "acte": acte_location.acte,
                "quantite": acte_location.quantite,
                "prix_unitaire": acte_location.prix_unitaire,
                "prix_total": acte_location.prix_total,
            }

    ecarts = []

    # Vérifier les actes inclus dans le forfait
    for acte_id, acte_inclus in actes_inclus.items():
        utilise = actes_utilises.get(
            acte_id,
            {
                "acte": acte_inclus.acte,
                "quantite": 0,
                "prix_unitaire": acte_inclus.prix_unitaire_inclus,
                "prix_total": Decimal("0"),
            },
        )

        ecart_quantite = utilise["quantite"] - acte_inclus.quantite

        # Calculate financial impact
        if ecart_quantite > 0:
            # Surplus charged at standard price
            prix_ecart = ecart_quantite * utilise["prix_unitaire"]
            economie = Decimal("0")
        elif ecart_quantite < 0:
            # Economy (included price not used)
            prix_ecart = Decimal("0")
            economie = abs(ecart_quantite * acte_inclus.prix_unitaire_inclus)
        else:
            prix_ecart = Decimal("0")
            economie = Decimal("0")

        ecarts.append(
            {
                "acte": acte_inclus.acte,
                "quantite_incluse": acte_inclus.quantite,
                "quantite_utilisee": utilise["quantite"],
                "ecart_quantite": ecart_quantite,
                "prix_unitaire_inclus": acte_inclus.prix_unitaire_inclus,
                "prix_unitaire_utilise": utilise["prix_unitaire"],
                "est_supplement": ecart_quantite > 0,
                "est_economie": ecart_quantite < 0,
                "prix_ecart": prix_ecart,
                "economie": economie,
                # Keep both for compatibility
                "impact_financier": prix_ecart if ecart_quantite > 0 else -economie,
                "type_ecart": (
                    "supplement"
                    if ecart_quantite > 0
                    else ("economie" if ecart_quantite < 0 else "equilibre")
                ),
            }
        )

    # Ajouter les actes supplémentaires (non inclus dans le forfait)
    for acte_id, utilise in actes_utilises.items():
        if acte_id not in actes_inclus:
            ecarts.append(
                {
                    "acte": utilise["acte"],
                    "quantite_incluse": 0,
                    "quantite_utilisee": utilise["quantite"],
                    "ecart_quantite": utilise["quantite"],
                    "prix_unitaire_inclus": Decimal("0"),
                    "prix_unitaire_utilise": utilise["prix_unitaire"],
                    "est_supplement": True,
                    "est_economie": False,
                    "prix_ecart": utilise["prix_total"],
                    "economie": Decimal("0"),
                    # Keep both for compatibility
                    "impact_financier": utilise["prix_total"],
                    "type_ecart": "supplement",
                }
            )

    return ecarts


def get_resume_financier_detaille(self):
    """
    Retourne un résumé financier complet de la location.
    """
    # Calculs de base
    totaux_consommations = ConsommationProduitBloc.calculer_totaux_par_location(self)
    ecarts_actes = self.get_ecarts_actes_forfait()

    # Calculs des actes - Fixed: Changed from self.actes to self.actes_location
    total_actes = sum(acte.prix_total for acte in self.actes_location.all())
    supplements_actes = sum(
        e["impact_financier"] for e in ecarts_actes if e["type_ecart"] == "supplement"
    )
    economies_actes = sum(
        abs(e["impact_financier"])
        for e in ecarts_actes
        if e["type_ecart"] == "economie"
    )

    return {
        "prix_base": self.prix_final,  # Fixed: was self.prix_base
        "prix_supplements_duree": self.prix_supplement_duree,  # Fixed: was self.prix_supplements_duree
        "prix_bloc_total": (self.prix_final or Decimal("0"))
        + self.prix_supplement_duree,
        "total_actes_supplementaires": total_actes,
        "supplements_actes_forfait": supplements_actes,
        "total_produits_utilises": totaux_consommations["total_utilise"],
        "total_produits_inclus": totaux_consommations["total_inclus"],
        "supplements_produits": totaux_consommations["total_supplements"],
        "economies_produits": totaux_consommations["total_economies"],
        "sous_total_avant_ajustements": (self.prix_final or Decimal("0"))
        + self.prix_supplement_duree
        + total_actes,
        "total_supplements": totaux_consommations["total_supplements"]
        + supplements_actes,
        "total_economies": totaux_consommations["total_economies"] + economies_actes,
        "montant_total_facture": self.montant_total_facture,
        "montant_paye_caisse": self.montant_paye_caisse,
        "statut_paiement": self.statut_paiement,
        "surplus_a_verser": self.surplus_a_verser,
        "complement_du_medecin": self.complement_du_medecin,
        "details_par_source": totaux_consommations["par_source"],
        "ecarts_actes_forfait": ecarts_actes,
    }


# Ajout de ces méthodes à la classe LocationBloc
LocationBloc.add_to_class('get_detail_consommations_par_source', get_detail_consommations_par_source)
LocationBloc.add_to_class('get_ecarts_actes_forfait', get_ecarts_actes_forfait)
LocationBloc.add_to_class('get_resume_financier_detaille', get_resume_financier_detaille)

# Assignation du manager personnalisé
LocationBloc.add_to_class('objects', LocationBlocManager())
