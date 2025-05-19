# rh/resources.py
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from import_export import fields, resources
from import_export.widgets import DecimalWidget, ForeignKeyWidget, Widget
from medical.models import Service

from .models import Personnel, Poste


class FKPosteWidget(ForeignKeyWidget):
    """
    Widget qui fait get_or_create sur Poste(label=value).
    """

    def clean(self, value, row=None, *args, **kwargs):
        if value is None or value == "":
            return None
        label = value.strip()
        # get_or_create directement
        poste, _ = self.get_queryset(value, row, **kwargs).get_or_create(label=label)
        return poste


class CleanDecimalWidget(Widget):
    """
    Convertit des chaînes comme "130 000.00" ou "130 000,00" en Decimal.
    """

    def clean(self, value, row=None, *args, **kwargs):
        if value is None or value == "":
            return None
        # On supprime tous les espaces (simples ou insécables)
        text = re.sub(r"[\s\u00A0]", "", str(value))
        # On remplace éventuellement la virgule décimale FR par un point
        text = text.replace(",", ".")
        try:
            return Decimal(text)
        except Exception as e:
            raise ValidationError(f"Impossible de convertir '{value}' en Decimal : {e}")


class StrictForeignKeyWidget(ForeignKeyWidget):
    """
    Lève une ValidationError si l'objet lié n'existe pas.
    """

    def clean(self, value, row=None, *args, **kwargs):
        if value is None or value == "":
            return None
        lookup = {self.field: value.strip()}
        try:
            return self.get_queryset(value, row, **kwargs).get(**lookup)
        except Service.DoesNotExist:
            # Construire un message comme celui de l'admin-import-export
            raise ValidationError(f"Service matching query does not exist: '{value}'")


class PersonnelResource(resources.ModelResource):
    service = fields.Field(
        column_name="service",
        attribute="service",
        widget=StrictForeignKeyWidget(Service, "name"),
    )
    poste = fields.Field(
        column_name="poste",
        attribute="poste",
        widget=FKPosteWidget(Poste, "label"),
    )
    salaire = fields.Field(
        column_name="salaire", attribute="salaire", widget=CleanDecimalWidget()
    )

    class Meta:
        model = Personnel
        import_id_fields = ["nom_prenom"]
        fields = ["nom_prenom", "service", "poste", "salaire"]
        skip_unchanged = True
        report_skipped = True


class PosteResource(resources.ModelResource):
    class Meta:
        model = Poste
        import_id_fields = ("label",)
        fields = ("label",)
        skip_unchanged = True
        report_skipped = True
