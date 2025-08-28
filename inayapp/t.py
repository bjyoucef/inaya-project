class Admission(Traceable):
    """Modèle pour les admissions hospitalières avec support des séjours courts"""

    STATUTS = [
        ("active", "Actif"),
        ("discharged", "Sorti"),
        ("transferred", "Transféré"),
        ("cancelled", "Annulé"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="admissions",
        verbose_name="Patient",
    )
    demande_admission = models.ForeignKey(
        "DemandeAdmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions",
        verbose_name="Demande d'admission",
    )
    medecin_traitant = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Médecin traitant",
    )
    date_admission = models.DateTimeField(
        default=timezone.now, verbose_name="Date d'admission"
    )
    date_sortie = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de sortie"
    )
    statut = models.CharField(
        max_length=20, choices=STATUTS, default="active", verbose_name="Statut"
    )
    cout_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût total",
    )
    notes_sortie = models.TextField(blank=True, verbose_name="Notes de sortie")
    est_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["-date_admission"]
        verbose_name = "Admission"
        verbose_name_plural = "Admissions"
        indexes = [models.Index(fields=["patient", "statut"])]

    def __str__(self):
        return f"Admission de {self.patient.nom_complet} - {self.date_admission.strftime('%d/%m/%Y %H:%M')}"

    @property
    def duree_sejour_heures(self) -> float:
        """Durée totale du séjour en heures"""
        end_date = self.date_sortie or timezone.now()
        delta = end_date - self.date_admission
        return delta.total_seconds() / 3600

    @property
    def duree_sejour(self) -> int:
        """Durée totale du séjour en jours (pour compatibilité)"""
        return max(
            1,
            int(self.duree_sejour_heures / 24)
            + (1 if self.duree_sejour_heures % 24 > 0 else 0),
        )

    def calculer_cout_total(self) -> Decimal:
        """Calcul précis basé sur chaque période de séjour avec gestion des séjours courts"""
        total = Decimal("0.00")

        for attribution in self.attributions_lits.all():
            if attribution.cout is not None:
                # Si le coût est déjà calculé et finalisé
                total += attribution.cout
            else:
                # Si l'attribution est encore en cours, calculer le coût actuel
                cout_attribution = attribution.calculer_cout()
                total += cout_attribution

        return total

    def get_resume_facturation(self) -> dict:
        """Retourne un résumé de la facturation avec détails des séjours courts"""
        total = self.calculer_cout_total()
        attributions = self.attributions_lits.all().order_by("date_debut")

        sejours_courts = []
        sejours_normaux = []

        for attr in attributions:
            details = attr.get_facturation_details()
            if attr.est_sejour_court:
                sejours_courts.append(details)
            else:
                sejours_normaux.append(details)

        return {
            "cout_total": float(total),
            "duree_totale_heures": round(self.duree_sejour_heures, 2),
            "duree_totale_jours": self.duree_sejour,
            "nombre_sejours_courts": len(sejours_courts),
            "nombre_sejours_normaux": len(sejours_normaux),
            "sejours_courts": sejours_courts,
            "sejours_normaux": sejours_normaux,
            "attributions_details": [
                attr.get_facturation_details() for attr in attributions
            ],
        }
