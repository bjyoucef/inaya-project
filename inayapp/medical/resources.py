# medical/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Service
from .models.bloc_location import Bloc, Forfait, LocationBloc, ActeLocation
from .models.prestation_Kt import PrestationKt
from patients.models import Patient
from medecin.models import Medecin


class ServiceResource(resources.ModelResource):
    class Meta:
        model = Service
        fields = (
            "id",
            "name",
            "color",
            "est_stockeur",
            "est_pharmacies",
            "est_hospitalier",
        )
        export_order = (
            "id",
            "name",
            "color",
            "est_stockeur",
            "est_pharmacies",
            "est_hospitalier",
        )


class BlocResource(resources.ModelResource):
    class Meta:
        model = Bloc
        fields = (
            "id",
            "nom_bloc",
            "prix_base",
            "prix_supplement_30min",
            "est_actif",
            "description",
        )
        export_order = (
            "id",
            "nom_bloc",
            "prix_base",
            "prix_supplement_30min",
            "est_actif",
            "description",
        )


class ForfaitResource(resources.ModelResource):
    class Meta:
        model = Forfait
        fields = (
            "id",
            "nom",
            "prix",
            "duree",
            "est_actif",
            "description",
            "date_creation",
            "date_modification",
        )
        export_order = (
            "id",
            "nom",
            "prix",
            "duree",
            "est_actif",
            "description",
            "date_creation",
            "date_modification",
        )


class LocationBlocResource(resources.ModelResource):
    patient_nom_complet = fields.Field(
        column_name="patient_nom_complet",
        attribute="patient",
        widget=ForeignKeyWidget(Patient, field="nom_complet"),
    )
    medecin_nom_complet = fields.Field(
        column_name="medecin_nom_complet",
        attribute="medecin",
        widget=ForeignKeyWidget(Medecin, field="nom_complet"),
    )

    class Meta:
        model = LocationBloc
        fields = (
            "id",
            "bloc__nom_bloc",
            "patient_nom_complet",
            "medecin_nom_complet",
            "date_operation",
            "heure_operation",
            "nom_acte",
            "type_tarification",
            "forfait__nom",
            "duree_reelle",
            "prix_final",
            "prix_supplement_duree",
            "montant_total_facture",
            "observations",
        )
        export_order = (
            "id",
            "bloc__nom_bloc",
            "patient_nom_complet",
            "medecin_nom_complet",
            "date_operation",
            "heure_operation",
            "nom_acte",
            "type_tarification",
            "forfait__nom",
            "duree_reelle",
            "prix_final",
            "prix_supplement_duree",
            "montant_total_facture",
            "observations",
        )


class ActeLocationResource(resources.ModelResource):
    class Meta:
        model = ActeLocation
        fields = (
            "id",
            "nom",
            "prix",
            "duree_estimee",
            "est_actif",
            "description",
            "date_creation",
            "date_modification",
        )
        export_order = (
            "id",
            "nom",
            "prix",
            "duree_estimee",
            "est_actif",
            "description",
            "date_creation",
            "date_modification",
        )


class PrestationKtResource(resources.ModelResource):
    patient_nom_complet = fields.Field(
        column_name="patient_nom_complet",
        attribute="patient",
        widget=ForeignKeyWidget(Patient, field="nom_complet"),
    )
    medecin_nom_complet = fields.Field(
        column_name="medecin_nom_complet",
        attribute="medecin",
        widget=ForeignKeyWidget(Medecin, field="nom_complet"),
    )

    class Meta:
        model = PrestationKt
        fields = (
            "id",
            "patient_nom_complet",
            "medecin_nom_complet",
            "date_prestation",
            "statut",
            "prix_total",
            "prix_supplementaire",
            "prix_supplementaire_medecin",
            "observations",
            "stock_impact_applied",
        )
        export_order = (
            "id",
            "patient_nom_complet",
            "medecin_nom_complet",
            "date_prestation",
            "statut",
            "prix_total",
            "prix_supplementaire",
            "prix_supplementaire_medecin",
            "observations",
            "stock_impact_applied",
        )
