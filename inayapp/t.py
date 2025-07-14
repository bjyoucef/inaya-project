# Dans votre modèle ExpressionBesoin (models.py)

from django.db import models
from django.contrib.auth.models import User
from datetime import datetime


class ExpressionBesoin(models.Model):
    STATUT_CHOICES = [
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validée"),
        ("REJETE", "Rejetée"),
        ("SERVIE", "Servie"),
    ]

    reference = models.CharField(max_length=100, unique=True, blank=True)
    service_demandeur = models.ForeignKey(
        "Service", on_delete=models.CASCADE, related_name="expressions_besoin"
    )
    service_approvisionneur = models.ForeignKey(
        "Service",
        on_delete=models.CASCADE,
        related_name="expressions_besoin_approvisionnees",
        null=True,
        blank=True,
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default="EN_ATTENTE"
    )
    valide_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expressions_besoin_validees",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="expressions_besoin_creees"
    )

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Expression de besoin"
        verbose_name_plural = "Expressions de besoin"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Générer la référence au format : EB-ANNÉE-SERVICE-USER
            year = datetime.now().year

            # Obtenir le code du service (3-4 premières lettres en majuscules)
            service_code = self.service_demandeur.nom[:4].upper().replace(" ", "")

            # Obtenir le nom de l'utilisateur (prénom ou username)
            user_code = (
                self.created_by.first_name[:4].upper()
                if self.created_by.first_name
                else self.created_by.username[:4].upper()
            )

            # Compter le nombre d'expressions de besoin pour ce service cette année
            count = (
                ExpressionBesoin.objects.filter(
                    date_creation__year=year, service_demandeur=self.service_demandeur
                ).count()
                + 1
            )

            # Générer la référence
            self.reference = f"EB-{year}-{service_code}-{user_code}-{count:03d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference or f"EB-{self.pk}"

    @property
    def total_articles(self):
        return self.lignes.count()


# Alternative : Si vous voulez une méthode plus simple avec juste un numéro séquentiel
class ExpressionBesoinSimple(models.Model):
    # ... autres champs ...

    def save(self, *args, **kwargs):
        if not self.reference:
            # Format : EB-AAAA-MM-NNN
            now = datetime.now()
            year = now.year
            month = now.month

            # Compter les expressions de besoin du mois
            count = (
                ExpressionBesoin.objects.filter(
                    date_creation__year=year, date_creation__month=month
                ).count()
                + 1
            )

            self.reference = f"EB-{year}-{month:02d}-{count:03d}"

        super().save(*args, **kwargs)


# Si vous préférez un format avec initiales du service uniquement
class ExpressionBesoinInitiales(models.Model):
    # ... autres champs ...

    def save(self, *args, **kwargs):
        if not self.reference:
            # Format : EB-SERVICE-AAAAMM-NNN
            now = datetime.now()

            # Obtenir les initiales du service
            service_initials = "".join(
                [word[0].upper() for word in self.service_demandeur.nom.split()[:3]]
            )

            # Compter les expressions de ce service ce mois-ci
            count = (
                ExpressionBesoin.objects.filter(
                    service_demandeur=self.service_demandeur,
                    date_creation__year=now.year,
                    date_creation__month=now.month,
                ).count()
                + 1
            )

            self.reference = (
                f"EB-{service_initials}-{now.year}{now.month:02d}-{count:03d}"
            )

        super().save(*args, **kwargs)
