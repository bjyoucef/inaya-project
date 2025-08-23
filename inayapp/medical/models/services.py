# medical/models/services.py

from django.db import models
import django.utils.timezone

class Service(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    est_stockeur = models.BooleanField(default=False)
    est_pharmacies = models.BooleanField(default=False)
    est_hospitalier = models.BooleanField(
        default=False, verbose_name="Service hospitalier"
    )
    est_actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name

    @property
    def total_beds(self):
        """Nombre total de lits dans le service"""
        return sum(room.bed_capacity for room in self.rooms.filter(is_active=True))

    @property
    def occupied_beds(self):
        """Nombre de lits occupés dans le service"""
        from .models import Bed

        return Bed.objects.filter(
            room__service=self, room__is_active=True, is_active=True, is_occupied=True
        ).count()

    @property
    def available_beds(self):
        """Nombre de lits disponibles dans le service"""
        from .models import Bed

        return Bed.objects.filter(
            room__service=self,
            room__is_active=True,
            is_active=True,
            is_occupied=False,
            maintenance_required=False,
        ).count()

    @property
    def occupancy_rate(self):
        """Taux d'occupation du service"""
        total = self.total_beds
        if total == 0:
            return 0
        return round((self.occupied_beds / total) * 100, 1)
