# export_data/views.py
from datetime import datetime
from django.apps import apps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from .utils import DataExporter
from .models import ExportHistory
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def export_data_view(request):
    """Vue principale pour l'export des données - VERSION CORRIGÉE"""
    exporter = DataExporter()
    all_models = exporter.get_all_models()

    context = {
        "all_models": all_models,
        "export_history": ExportHistory.objects.filter(user=request.user).order_by(
            "-created_at"
        )[:10],
    }

    if request.method == "POST":
        selected_models = {}
        export_format = request.POST.get("export_format", "csv")

        logger.info(f"Données POST reçues: {dict(request.POST)}")

        # Récupérer les modèles sélectionnés - MÉTHODE CORRIGÉE
        for key, value in request.POST.items():
            if key.startswith("model_") and value == "on":
                # Format: model_app_label.ModelName
                model_key = key.replace("model_", "")

                if "." in model_key:
                    app_label, model_name = model_key.split(".", 1)

                    # Vérifier que l'app existe
                    try:
                        apps.get_app_config(app_label)
                        if app_label not in selected_models:
                            selected_models[app_label] = []
                        selected_models[app_label].append(model_name)
                        logger.info(f"Modèle sélectionné: {app_label}.{model_name}")
                    except LookupError:
                        logger.error(f"App '{app_label}' non trouvée, ignoré")
                        continue

        logger.info(f"Modèles sélectionnés finaux: {selected_models}")

        if not selected_models:
            messages.error(
                request, "Veuillez sélectionner au moins un modèle à exporter."
            )
            return render(request, "export_data/index.html", context)

        try:
            # Préparer les données
            exporter.prepare_data(selected_models)

            # Compter le nombre total d'enregistrements
            total_records = sum(info["count"] for info in exporter.models_data.values())

            if total_records == 0:
                messages.warning(
                    request,
                    "Aucun enregistrement trouvé dans les modèles sélectionnés.",
                )
                return render(request, "export_data/index.html", context)

            # Créer l'historique
            history = ExportHistory.objects.create(
                user=request.user,
                exported_models=json.dumps(selected_models),
                export_format=export_format,
                file_path=f"export_{export_format}_{request.user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                records_count=total_records,
            )

            logger.info(f"Export créé: {history.id}, {total_records} enregistrements")

            # Export selon le format
            if export_format == "csv":
                response = exporter.export_to_csv()
            elif export_format == "excel":
                response = exporter.export_to_excel()
            elif export_format == "json":
                response = exporter.export_to_json()
            else:
                messages.error(
                    request, f"Format d'export '{export_format}' non supporté."
                )
                return render(request, "export_data/index.html", context)

            # Marquer l'export comme réussi
            history.status = "completed"
            history.save()

            messages.success(
                request, f"Export réussi: {total_records} enregistrements exportés."
            )
            return response

        except Exception as e:
            logger.error(f"Erreur lors de l'export: {str(e)}", exc_info=True)
            messages.error(request, f"Erreur lors de l'export: {str(e)}")

    return render(request, "export_data/index.html", context)


@login_required
@require_http_methods(["GET"])
def get_model_preview(request):
    """API pour prévisualiser les données d'un modèle - VERSION CORRIGÉE"""
    app_label = request.GET.get("app")
    model_name = request.GET.get("model")

    # Validation des paramètres
    if not app_label or not model_name:
        return JsonResponse(
            {"success": False, "error": "Paramètres 'app' et 'model' requis"}
        )

    try:
        # Vérifier que l'app existe
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            return JsonResponse(
                {"success": False, "error": f"Application '{app_label}' non trouvée"}
            )

        # Vérifier que le modèle existe
        try:
            model_class = apps.get_model(app_label, model_name)
        except LookupError:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Modèle '{model_name}' non trouvé dans l'application '{app_label}'",
                }
            )

        # Récupérer les informations du modèle
        total_count = model_class.objects.count()

        # Récupérer les 5 premiers enregistrements
        queryset = model_class.objects.all()[:5]
        preview_data = []
        fields = []

        # Obtenir les noms des champs
        fields = [field.name for field in model_class._meta.fields]

        # Traiter chaque enregistrement
        for obj in queryset:
            obj_data = {}
            for field_name in fields:
                try:
                    value = getattr(obj, field_name)
                    if value is None:
                        obj_data[field_name] = ""
                    elif hasattr(value, "strftime"):  # DateTime/Date
                        obj_data[field_name] = value.strftime("%Y-%m-%d %H:%M:%S")
                    elif hasattr(value, "__str__"):
                        str_value = str(value)
                        # Limiter la longueur pour la prévisualisation
                        if len(str_value) > 100:
                            obj_data[field_name] = str_value[:100] + "..."
                        else:
                            obj_data[field_name] = str_value
                    else:
                        obj_data[field_name] = str(value)
                except Exception as e:
                    logger.warning(
                        f"Erreur lors de la récupération du champ {field_name}: {e}"
                    )
                    obj_data[field_name] = f"Erreur: {str(e)}"
            preview_data.append(obj_data)

        # Informations sur les champs pour améliorer l'affichage
        field_info = []
        for field in model_class._meta.fields:
            field_info.append(
                {
                    "name": field.name,
                    "verbose_name": getattr(field, "verbose_name", field.name),
                    "type": field.__class__.__name__,
                }
            )

        logger.info(
            f"Prévisualisation réussie pour {app_label}.{model_name}: {len(preview_data)} enregistrements"
        )

        return JsonResponse(
            {
                "success": True,
                "fields": fields,
                "field_info": field_info,
                "data": preview_data,
                "total_count": total_count,
                "preview_count": len(preview_data),
                "model_verbose_name": getattr(
                    model_class._meta, "verbose_name", model_name
                ),
            }
        )

    except Exception as e:
        logger.error(
            f"Erreur preview pour {app_label}.{model_name}: {str(e)}", exc_info=True
        )
        return JsonResponse({"success": False, "error": f"Erreur interne: {str(e)}"})


@login_required
def export_history_view(request):
    """Vue pour afficher l'historique complet des exports"""
    history_list = ExportHistory.objects.filter(user=request.user).order_by(
        "-created_at"
    )

    paginator = Paginator(history_list, 20)  # 20 exports par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {"page_obj": page_obj, "total_exports": history_list.count()}

    return render(request, "export_data/history.html", context)


@login_required
def debug_apps(request):
    """Vue de debug pour voir les apps disponibles"""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"})

    apps_info = []
    for app_config in apps.get_app_configs():
        models_info = []
        try:
            for model in app_config.get_models():
                try:
                    count = model.objects.count()
                    models_info.append(
                        {
                            "name": model.__name__,
                            "label": model._meta.label,
                            "app_label": model._meta.app_label,
                            "verbose_name": getattr(
                                model._meta, "verbose_name", model.__name__
                            ),
                            "count": count,
                        }
                    )
                except Exception as e:
                    models_info.append({"name": model.__name__, "error": str(e)})
        except Exception as e:
            models_info.append({"error": f"Erreur app: {str(e)}"})

        apps_info.append(
            {
                "name": app_config.name,
                "label": app_config.label,
                "verbose_name": getattr(app_config, "verbose_name", app_config.name),
                "models": models_info,
            }
        )

    return JsonResponse({"apps": apps_info}, indent=2)
