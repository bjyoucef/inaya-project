from django.db import models



class Medecin(models.Model):
    """Modèle pour gérer les médecins avec lien vers le personnel"""

    personnel = models.OneToOneField(
        "rh.Personnel",
        on_delete=models.CASCADE,
        related_name="profil_medecin",
        verbose_name="Profil du personnel",
    )

    # Utilisation de ManyToManyField pour permettre plusieurs services
    services = models.ManyToManyField(
        'medical.Services',  # Référence string
        related_name='medecins'
    )
    specialite = models.CharField(max_length=100, verbose_name="Spécialité médicale")
    numero_ordre = models.CharField(
        max_length=50, unique=True, verbose_name="Numéro d'ordre"
    )
    photo_profil = models.ImageField(
        upload_to="medecins/profiles/",
        null=True,
        blank=True,
        verbose_name="Photo de profil",
    )
    disponible = models.BooleanField(
        default=True, verbose_name="Disponible pour consultations"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )

    @property
    def nom_complet(self):
        return f"{self.personnel.user.first_name} {self.personnel.user.last_name}"

    def __str__(self):
        return f"Dr. {self.nom_complet} ({self.specialite})"

    class Meta:
        verbose_name = "Médecin"
        verbose_name_plural = "Médecins"
