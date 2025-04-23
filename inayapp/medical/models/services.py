import re

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Service(models.Model):
    id_service = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7, blank=True, null=True)

    class Meta:
        db_table = "service"
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        content_type = ContentType.objects.get_for_model(self)
        codename = self._generate_codename()
        name = f"Voir le service {self.name}"
        Permission.objects.update_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": name},
        )

    def delete(self, *args, **kwargs):
        content_type = ContentType.objects.get_for_model(self)
        Permission.objects.filter(
            codename=self._generate_codename(), content_type=content_type
        ).delete()
        super().delete(*args, **kwargs)

    def _generate_codename(self):
        base = re.sub(r"[^a-zA-Z0-9_]", "", self.name.replace(" ", "_")).lower()
        return f"view_service_{base}"[:100]
