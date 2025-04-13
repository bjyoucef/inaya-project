# helpdesk.models.py
from django.db import models

class Helpdesk(models.Model):
    ip_address = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    details = models.TextField()
    file_path = models.CharField(max_length=1000, blank=True, null=True)
    audio_path = models.CharField(max_length=255, blank=True, null=True)
    time_send = models.DateTimeField(blank=True, null=True)
    time_terminee = models.DateField(blank=True, null=True)
    terminee_par = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} {self.type}"
    
    class Meta:
        managed = True
        db_table = 'helpdesk'
        permissions = (
            ("ACCES_AU_DEPARTEMENT_IT", "Accès au département IT"),
            ("ACCES_AU_DEPARTEMENT_TECHNIQUE", "Accès au département Technique"),
            ("ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT", "Accès au département Approvisionnement"),
        )
