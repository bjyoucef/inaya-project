import re

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db import models
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
import re

# prix_joure = models.DecimalField(
#     max_digits=10, decimal_places=2, blank=True, null=True
# )
# prix_nuit = models.DecimalField(
#     max_digits=10, decimal_places=2, blank=True, null=True
# )
# prix_24h = models.DecimalField(
#     max_digits=10, decimal_places=2, blank=True, null=True
# )
# salaire = models.DecimalField(
#     max_digits=10, decimal_places=2, blank=True, null=True
# )

class Services(models.Model):
    id_service = models.AutoField(primary_key=True)
    service_name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, blank=True, null=True)

    def __str__(self):
        return self.service_name

    def save(self, *args, **kwargs):
        # Sauvegarde d'abord l'objet
        super().save(*args, **kwargs)

        # Génération automatique de la permission
        content_type = ContentType.objects.get_for_model(Services)
        codename = self._generate_codename()
        name = f"Voir le service {self.service_name}"

        # Création ou mise à jour de la permission
        Permission.objects.update_or_create(
            codename=codename, content_type=content_type, defaults={"name": name}
        )

    def delete(self, *args, **kwargs):
        # Suppression de la permission associée
        content_type = ContentType.objects.get_for_model(Services)
        Permission.objects.filter(
            codename=self._generate_codename(), content_type=content_type
        ).delete()
        super().delete(*args, **kwargs)

    def _generate_codename(self):
        # Génère un nom de code valide pour les permissions
        base_name = re.sub(
            r"[^a-zA-Z0-9_]", "", self.service_name.replace(" ", "_")
        ).lower()
        return f"view_service_{base_name}"[:100]

    class Meta:
        managed = True
        db_table = "services"
