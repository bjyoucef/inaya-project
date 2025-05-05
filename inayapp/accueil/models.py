# accueil/models.py
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from django.db import models
from django.db import models


from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from django.db import models
from django.core.exceptions import ValidationError


class PermissionMixin:
    """Mixin pour la gestion automatique des permissions"""

    def generate_permission(self, prefix: str, name_field: str = "label") -> str:
        """Génère une permission selon un modèle standard"""
        # Validation du champ de nom
        name_value = getattr(self, name_field, None)
        if not name_value:
            raise ValidationError(
                f"Le champ {name_field} est requis pour générer la permission"
            )

        # Génération des éléments de la permission
        app_label = self._meta.app_label
        model_name = self._meta.model_name.lower()
        codename = f"view_{prefix}_{slugify(name_value).replace('-', '_')}"
        permission_name = f"Peut voir {self._meta.verbose_name} {name_value}"

        # Création du ContentType
        content_type = ContentType.objects.get_for_model(self.__class__)

        # Création/Mise à jour de la permission
        permission, created = Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": permission_name},
        )

        return f"{app_label}.{codename}"


class MenuGroup(models.Model, PermissionMixin):
    name = models.CharField("Nom du groupe", max_length=255)
    icon = models.CharField(
        "Icône", max_length=255, help_text="Classe CSS de l'icône (ex: fas fa-home)"
    )
    order = models.IntegerField("Ordre", default=0)
    permission = models.CharField(
        "Permission requise",
        max_length=255,
        blank=True,
        null=True,
        help_text="Format: app_label.permission_codename",
    )

    class Meta:
        verbose_name = "Groupe de menu"
        verbose_name_plural = "Groupes de menus"
        ordering = ["order"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.permission:
            self.permission = self.generate_permission(
                prefix="menu_group", name_field="name"
            )
        super().save(*args, **kwargs)


class MenuItem(models.Model, PermissionMixin):
    group = models.ForeignKey(
        MenuGroup,
        verbose_name="Groupe parent",
        on_delete=models.CASCADE,
        related_name="items",
    )
    route = models.CharField("Route", max_length=255, help_text="Nom de la vue ou URL")
    label = models.CharField("Libellé", max_length=255)
    icon = models.CharField("Icône", max_length=255)
    permission = models.CharField(
        "Permission requise",
        max_length=255,
        blank=True,
        null=True,
        help_text="Format: app_label.permission_codename",
    )
    order = models.IntegerField("Ordre", default=0)

    class Meta:
        verbose_name = "Élément de menu"
        verbose_name_plural = "Éléments de menu"
        ordering = ["order"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        if not self.permission:
            self.permission = self.generate_permission(prefix="menu_item")
        super().save(*args, **kwargs)


class NavbarItem(models.Model, PermissionMixin):
    TYPE_CHOICES = [
        ("title", "Titre"),
        ("link", "Lien"),
    ]

    menu_item = models.ForeignKey(
        MenuItem,
        verbose_name="Élément associé",
        on_delete=models.CASCADE,
        related_name="navbar_items",
        null=True,
        blank=True,
    )
    type = models.CharField("Type", max_length=10, choices=TYPE_CHOICES)
    label = models.CharField("Libellé", max_length=255)
    icon = models.CharField(
        "Icône",
        max_length=50,
        blank=True,
        null=True,
        help_text="Classe Font Awesome (ex: fas fa-home)",
    )
    url_name = models.CharField("Nom de la vue", max_length=255)
    order = models.IntegerField("Ordre", default=0)
    permission = models.CharField(
        "Permission requise",
        max_length=255,
        blank=True,
        null=True,
        help_text="Format: app_label.permission_codename",
    )

    class Meta:
        verbose_name = "Élément de navigation"
        verbose_name_plural = "Éléments de navigation"
        ordering = ["order"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.label}"

    def save(self, *args, **kwargs):
        if not self.permission:
            self.permission = self.generate_permission(prefix="navbar_item")
        super().save(*args, **kwargs)


class ConfigDate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING, blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    page = models.CharField(max_length=50)

    class Meta:
        managed = True


class Theme(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    theme = models.CharField(
        max_length=10,
        choices=[("light", "Clair"), ("dark", "Sombre")],
        default="light",
    )

    def __str__(self):
        return f"Profil de {self.user.username}"
