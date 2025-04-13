from django.db import models
from filer.fields.file import FilerFileField


class Documents(models.Model):
    nom = models.CharField(max_length=100)
    fichier = FilerFileField(
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='documents'
    )

    def __str__(self):
        return self.nom

    class Meta:
        permissions = (
            ('view_document', 'Peut visualiser le document'),
            ('download_document', 'Peut télécharger le document'),
        )
