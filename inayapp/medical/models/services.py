# medical/models/services.py

from django.db import models


class Service(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    est_stockeur = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name
