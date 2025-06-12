# export_data / utils.py
import csv
import json
import xlsxwriter
from django.apps import apps
from django.http import HttpResponse
from django.core.serializers import serialize
from django.db.models import Model
from io import BytesIO
from datetime import datetime
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DataExporter:
    """Classe pour gérer l'export des données"""

    def __init__(self):
        self.models_data = {}

    def get_all_models(self):
        """Récupère tous les modèles du projet"""
        all_models = {}

        # Apps à exclure par défaut
        EXCLUDED_APPS = [
            "django.contrib.admin",
            # "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
            "export_data",
            "filer",
            "easy_thumbnails",
        ]

        for app_config in apps.get_app_configs():
            if app_config.name not in EXCLUDED_APPS:
                app_models = []
                try:
                    for model in app_config.get_models():
                        # Vérifier que le modèle a des données ou peut être interrogé
                        try:
                            count = model.objects.count()
                            app_models.append(
                                {
                                    "name": model.__name__,
                                    "model": model,
                                    "verbose_name": getattr(
                                        model._meta, "verbose_name", model.__name__
                                    ),
                                    "count": count,
                                    "app_label": app_config.label,  # Ajouter le label de l'app
                                }
                            )
                        except Exception as e:
                            logger.warning(
                                f"Impossible de compter les objets pour {model.__name__}: {e}"
                            )
                            continue

                    if app_models:
                        all_models[app_config.label] = (
                            {  # Utiliser le label au lieu du nom
                                "verbose_name": app_config.verbose_name
                                or app_config.name,
                                "models": app_models,
                            }
                        )
                except Exception as e:
                    logger.error(
                        f"Erreur lors du traitement de l'app {app_config.name}: {e}"
                    )
                    continue

        return all_models

    def prepare_data(self, selected_models):
        """Prépare les données pour l'export - VERSION CORRIGÉE"""
        self.models_data = {}

        logger.info(f"Préparation des données pour: {selected_models}")

        for app_label, model_names in selected_models.items():
            logger.info(f"Traitement de l'app: {app_label}")

            # Vérifier que l'app existe
            try:
                app_config = apps.get_app_config(app_label)
            except LookupError:
                logger.error(
                    f"Application '{app_label}' non trouvée. Apps disponibles: {[ac.label for ac in apps.get_app_configs()]}"
                )
                continue

            for model_name in model_names:
                try:
                    # Utiliser le label de l'app au lieu du nom
                    model_class = apps.get_model(app_label, model_name)
                    logger.info(f"Traitement du modèle: {app_label}.{model_name}")

                    queryset = model_class.objects.all()

                    # Convertir en données sérialisables
                    data = []
                    for obj in queryset:
                        obj_data = {}
                        for field in model_class._meta.fields:
                            try:
                                value = getattr(obj, field.name)
                                # Gérer les différents types de champs
                                if value is None:
                                    obj_data[field.name] = ""
                                elif hasattr(value, "strftime"):  # DateTime
                                    obj_data[field.name] = value.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                elif hasattr(value, "__str__"):
                                    obj_data[field.name] = str(value)
                                else:
                                    obj_data[field.name] = value
                            except Exception as e:
                                logger.warning(
                                    f"Erreur lors de la récupération du champ {field.name}: {e}"
                                )
                                obj_data[field.name] = "Erreur"
                        data.append(obj_data)

                    model_key = f"{app_label}.{model_name}"
                    self.models_data[model_key] = {
                        "data": data,
                        "verbose_name": model_class._meta.verbose_name_plural
                        or model_name,
                        "count": len(data),
                    }

                    logger.info(
                        f"Modèle {model_key}: {len(data)} enregistrements préparés"
                    )

                except LookupError:
                    logger.error(
                        f"Modèle '{model_name}' non trouvé dans l'app '{app_label}'"
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Erreur lors du traitement de {app_label}.{model_name}: {e}"
                    )
                    continue

    def export_to_csv(self):
        """Export en CSV"""
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="export_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)

        for model_key, model_info in self.models_data.items():
            if model_info["data"]:
                # Titre du modèle
                writer.writerow(
                    [
                        f"=== {model_info['verbose_name']} ({model_info['count']} enregistrements) ==="
                    ]
                )

                # En-têtes
                headers = list(model_info["data"][0].keys())
                writer.writerow(headers)

                # Données
                for row in model_info["data"]:
                    writer.writerow([str(row.get(header, "")) for header in headers])

                writer.writerow([])  # Ligne vide entre les modèles

        return response

    def export_to_excel(self):
        """Export en Excel"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        # Styles
        header_format = workbook.add_format(
            {"bold": True, "font_color": "white", "bg_color": "#4472C4", "border": 1}
        )

        data_format = workbook.add_format({"border": 1})

        for model_key, model_info in self.models_data.items():
            if model_info["data"]:
                # Créer une feuille par modèle (nom sécurisé pour Excel)
                sheet_name = model_key.replace(".", "_")[:31]
                worksheet = workbook.add_worksheet(sheet_name)

                # En-têtes
                headers = list(model_info["data"][0].keys())
                for col, header in enumerate(headers):
                    worksheet.write(0, col, header, header_format)

                # Données
                for row_idx, row_data in enumerate(model_info["data"], 1):
                    for col_idx, header in enumerate(headers):
                        value = str(row_data.get(header, ""))
                        worksheet.write(row_idx, col_idx, value, data_format)

                # Ajuster la largeur des colonnes
                for col_idx in range(len(headers)):
                    worksheet.set_column(col_idx, col_idx, 15)

        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="export_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        )

        return response

    def export_to_json(self):
        """Export en JSON"""
        response = HttpResponse(content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="export_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
        )

        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_models": len(self.models_data),
            "total_records": sum(info["count"] for info in self.models_data.values()),
            "models": self.models_data,
        }

        json.dump(export_data, response, ensure_ascii=False, indent=2)
        return response
