from django.db import models

class Contacts(models.Model):
    nom = models.CharField(max_length=255)
    poste = models.CharField(max_length=255)
    numero = models.CharField(max_length=255, blank=True, null=True)
    statut_activite = models.BooleanField(default=True)
    user_add = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.nom} - {self.numero}"
    
    class Meta:
        managed = True
        db_table = 'contacts'
