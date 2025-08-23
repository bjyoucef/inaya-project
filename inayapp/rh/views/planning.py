import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from medical.models import Service
from utils.utils import services_autorises
from xhtml2pdf import pisa

from ..models import (HonorairesActe, Personnel, Planning, PointagesActes,
                      Poste, Shift, Tarif_Gardes)

logger = logging.getLogger(__name__)

# Dans views.py


def refresh_csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


# Fonction utilitaire pour les réponses JSON standardisées
def json_response(success=True, message="", data=None, status=200):
    """Fonction utilitaire pour standardiser les réponses JSON"""
    response_data = {"success": success, "message": message}
    if data is not None:
        response_data["data"] = data

    return JsonResponse(response_data, status=status)


def extract_filters_short(request):
    """Extract filters using IDs instead of names for shorter URLs"""
    return {
        "service_id": request.GET.get("s", "all"),
        "poste_id": request.GET.get("p", "all"),
        "employee_id": request.GET.get("e", "all"),
        "shift_id": request.GET.get("sh", "all"),
        "start_date": request.GET.get("sd", ""),
        "end_date": request.GET.get("ed", ""),
    }


def build_redirect_params(filters):
    """Build redirect parameters with shorter URLs"""
    params = {}
    if filters.get("service_id") != "all":
        params["s"] = str(filters["service_id"])
    if filters.get("poste_id") != "all":
        params["p"] = str(filters["poste_id"])
    if filters.get("employee_id") != "all":
        params["e"] = str(filters["employee_id"])
    if filters.get("shift_id") != "all":
        params["sh"] = str(filters["shift_id"])
    if filters.get("start_date"):
        params["sd"] = filters["start_date"]
    if filters.get("end_date"):
        params["ed"] = filters["end_date"]
    return "?" + urlencode(params) if params else ""


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def planning(request):
    filters = extract_filters_short(request)

    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="planning",
        defaults={"start_date": date.today(), "end_date": date.today()},
    )

    if filters["start_date"]:
        try:
            config.start_date = datetime.strptime(
                filters["start_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            config.start_date = date.today()
    if filters["end_date"]:
        try:
            config.end_date = datetime.strptime(filters["end_date"], "%Y-%m-%d").date()
        except ValueError:
            config.end_date = date.today()
    config.save()

    start_date = filters["start_date"] or config.start_date
    end_date = filters["end_date"] or config.end_date
    filters["start_date"] = (
        start_date.isoformat() if isinstance(start_date, date) else start_date
    )
    filters["end_date"] = (
        end_date.isoformat() if isinstance(end_date, date) else end_date
    )

    # Build query filters using IDs
    planning_filter = Q(shift_date__range=[filters["start_date"], filters["end_date"]])
    pointage_filter = Q(
        planning__shift_date__range=[filters["start_date"], filters["end_date"]]
    )

    if filters["service_id"] != "all":
        planning_filter &= Q(service_id=filters["service_id"])
        pointage_filter &= Q(planning__service_id=filters["service_id"])
    if filters["poste_id"] != "all":
        planning_filter &= Q(poste_id=filters["poste_id"])
        pointage_filter &= Q(planning__poste_id=filters["poste_id"])
    if filters["employee_id"] != "all":
        planning_filter &= Q(employee_id=filters["employee_id"])
        pointage_filter &= Q(planning__employee_id=filters["employee_id"])
    if filters["shift_id"] != "all":
        planning_filter &= Q(shift_id=filters["shift_id"])
        pointage_filter &= Q(planning__shift_id=filters["shift_id"])

    try:
        plannings_validees = Planning.objects.select_related(
            "employee", "service", "shift", "poste"
        ).filter(
            planning_filter, pointage_created_at__isnull=False, decharge__isnull=True
        )

        plannings = Planning.objects.select_related(
            "employee", "service", "shift", "poste"
        ).filter(planning_filter)

        pointages = (
            PointagesActes.objects.select_related(
                "planning__employee", "planning__service", "acte", "planning__shift"
            )
            .filter(pointage_filter)
            .order_by("planning__shift_date")
        )
    except Exception as e:
        logger.exception("Erreur lors du filtrage des plannings: %s", e)
        plannings = plannings_validees = pointages = Planning.objects.none()

    # Get selected objects for display
    selected_service = None
    selected_poste = None
    selected_employee = None
    selected_shift = None

    if filters["service_id"] != "all":
        try:
            selected_service = Service.objects.get(id=filters["service_id"])
        except Service.DoesNotExist:
            pass

    if filters["poste_id"] != "all":
        try:
            selected_poste = Poste.objects.get(id=filters["poste_id"])
        except Poste.DoesNotExist:
            pass

    if filters["employee_id"] != "all":
        try:
            selected_employee = Personnel.objects.get(id=filters["employee_id"])
        except Personnel.DoesNotExist:
            pass

    if filters["shift_id"] != "all":
        try:
            selected_shift = Shift.objects.get(id=filters["shift_id"])
        except Shift.DoesNotExist:
            pass

    services = services_autorises(request.user)
    employees = Personnel.objects.filter(
        statut_activite=True, use_in_planning=True
    ).order_by("nom_prenom")
    postes = Poste.objects.order_by("label")
    shifts = Shift.objects.order_by("label")
    service_colors = {s.name: s.color for s in services}

    # Build events
    events = []
    for p in plannings:
        shift = p.shift
        title = f"{p.employee.nom_prenom} - {shift.label if shift else 'No Shift'} - {p.poste.label if p.poste else 'No Poste'}"
        start_time = shift.debut if shift and shift.debut else datetime.min.time()
        end_time = shift.fin if shift and shift.fin else datetime.min.time()
        event_start = datetime.combine(p.shift_date, start_time)
        event_end = datetime.combine(p.shift_date, end_time) + (
            timedelta(days=1) if end_time < start_time else timedelta()
        )
        events.append(
            {
                "id": p.id,
                "service_id": p.service.id,
                "id_poste": p.poste.id if p.poste else None,
                "title": title,
                "start": event_start.isoformat(),
                "end": event_end.isoformat(),
                "backgroundColor": (
                    "gray"
                    if p.pointage_created_at
                    else service_colors.get(p.service.name, "black")
                ),
            }
        )

    # Calculate pointage totals
    for pa in pointages:
        if pa.acte:
            pa.total = pa.acte.prix_acte * pa.nbr_actes
        else:
            pa.total = Decimal("0.00")

    # Group plannings
    grouped_plannings = defaultdict(
        lambda: {
            "employee": None,
            "prix_total": Decimal(0),
            "prix_acte_total": Decimal(0),
            "pointagesDetail": [],
        }
    )

    for planning in plannings_validees:
        emp_id = planning.employee.id
        grouped = grouped_plannings[emp_id]
        grouped["employee"] = planning.employee
        grouped["prix_total"] += planning.prix or 0
        grouped["prix_acte_total"] += planning.prix_acte or 0
        grouped["pointagesDetail"].append(
            {
                "service_name": planning.service.name,
                "date_pointage": planning.shift_date.strftime("%Y-%m-%d"),
                "shift": planning.shift.label if planning.shift else "",
                "prix": planning.prix,
                "prix_acte": planning.prix_acte,
            }
        )

    # Prepare selected data for template
    selected_data = {
        "service": selected_service.name if selected_service else "all",
        "service_id": filters["service_id"],
        "poste": selected_poste.label if selected_poste else "all",
        "poste_id": filters["poste_id"],
        "employee_id": filters["employee_id"],
        "employee": selected_employee,
        "shift": selected_shift.code if selected_shift else "all",
        "shift_id": filters["shift_id"],
        "start_date": filters["start_date"],
        "end_date": filters["end_date"],
    }

    context = {
        "planningsValidees": list(grouped_plannings.values()),
        "employees": employees,
        "postes": postes,
        "services": services,
        "events": events,
        "selected": selected_data,
        "title": "Plannings",
        "user": request.user,
        "pointages": pointages,
        "shifts": shifts,
    }
    return render(request, "planning/planning.html", context)


@permission_required("rh.creer_planning", raise_exception=True)
def save_planning(request):
    if request.method != "POST":
        return redirect(reverse("planning") + f"?{request.GET.urlencode()}")

    # Récupération des données
    service_id = request.POST.get("service_id")
    poste_id = request.POST.get("poste_id")
    employee_id = request.POST.get("employee_id")
    shift_id = request.POST.get("shift_id")
    shift_date_str = request.POST.get("date")
    event_id = request.POST.get("event_id")

    # URL de redirection avec filtres conservés
    redirect_url = reverse("planning") + f"?{request.GET.urlencode()}"

    # Validation des données d'entrée
    if not all([service_id, poste_id, employee_id, shift_id, shift_date_str]):
        messages.error(request, "❌ Tous les champs sont obligatoires.")
        return redirect(redirect_url)

    # Validation des IDs
    if any(val == "all" for val in [service_id, poste_id, employee_id, shift_id]):
        messages.error(
            request,
            "❌ Veuillez sélectionner des valeurs spécifiques pour tous les champs.",
        )
        return redirect(redirect_url)

    try:
        shift_date = datetime.strptime(shift_date_str, "%Y-%m-%d").date()



        service = get_object_or_404(Service, id=service_id)
        poste = get_object_or_404(Poste, id=poste_id)
        employee = get_object_or_404(Personnel, id=employee_id)
        shift = get_object_or_404(Shift, id=shift_id)

        # Vérification du statut de l'employé
        if not employee.statut_activite:
            messages.error(
                request, f"❌ L'employé {employee.nom_prenom} n'est pas actif."
            )
            return redirect(redirect_url)

        if not employee.use_in_planning:
            messages.error(
                request,
                f"❌ L'employé {employee.nom_prenom} n'est pas autorisé dans les plannings.",
            )
            return redirect(redirect_url)

        with transaction.atomic():
            if event_id:
                # Mise à jour d'un planning existant
                planning = get_object_or_404(Planning, id=event_id)

                # Vérifier si le planning n'est pas déjà validé
                if planning.pointage_created_at:
                    messages.error(
                        request, "❌ Impossible de modifier un planning déjà validé."
                    )
                    return redirect(redirect_url)

                # Vérifier si la nouvelle date/employé crée un conflit
                if (
                    planning.employee_id != int(employee_id)
                    or planning.shift_date != shift_date
                ):
                    existing = (
                        Planning.objects.filter(
                            employee_id=employee_id, shift_date=shift_date
                        )
                        .exclude(id=event_id)
                        .exists()
                    )

                    if existing:
                        messages.error(
                            request,
                            f"❌ L'employé {employee.nom_prenom} est déjà planifié le {shift_date.strftime('%d/%m/%Y')}.",
                        )
                        return redirect(redirect_url)

                # Sauvegarder les anciennes valeurs pour le log
                old_date = planning.shift_date
                old_employee = planning.employee.nom_prenom

                planning.service = service
                planning.poste = poste
                planning.shift_date = shift_date
                planning.shift = shift
                planning.employee = employee
                planning.save()

                logger.info(
                    f"Planning {event_id} mis à jour: {old_employee} ({old_date}) -> {employee.nom_prenom} ({shift_date})"
                )
                messages.success(
                    request,
                    f"✅ Planning mis à jour avec succès pour {employee.nom_prenom}.",
                )

            else:
                # Création d'un nouveau planning
                # Vérifier si l'employé est déjà planifié pour cette date
                existing = Planning.objects.filter(
                    employee_id=employee_id, shift_date=shift_date
                ).exists()

                if existing:
                    messages.error(
                        request,
                        f"❌ L'employé {employee.nom_prenom} est déjà planifié le {shift_date.strftime('%d/%m/%Y')}.",
                    )
                    return redirect(redirect_url)

                planning = Planning.objects.create(
                    service=service,
                    poste=poste,
                    shift_date=shift_date,
                    shift=shift,
                    employee=employee,
                    created_by=request.user.personnel,
                    created_at=timezone.now(),
                )

                logger.info(
                    f"Nouveau planning créé: {employee.nom_prenom} - {service.name} - {shift_date}"
                )
                messages.success(
                    request,
                    f"✅ Planning ajouté avec succès pour {employee.nom_prenom} le {shift_date.strftime('%d/%m/%Y')}.",
                )

    except IntegrityError as e:
        if "unique_employee_per_date" in str(e):
            messages.error(
                request,
                f"❌ L'employé {employee.nom_prenom} est déjà planifié le {shift_date.strftime('%d/%m/%Y')}.",
            )
        else:
            logger.exception(
                "Erreur d'intégrité lors de l'enregistrement du planning: %s", e
            )
            messages.error(request, "❌ Erreur d'intégrité dans la base de données.")
    except ValidationError as e:
        if hasattr(e, "message_dict") and "employee" in e.message_dict:
            messages.error(request, f"❌ {e.message_dict['employee'][0]}")
        else:
            messages.error(request, f"❌ Erreur de validation: {str(e)}")
    except Exception as e:
        logger.exception("Erreur lors de l'enregistrement du planning: %s", e)
        messages.error(
            request, "❌ Erreur inattendue lors de l'enregistrement du planning."
        )

    return redirect(redirect_url)

@permission_required("rh.modifier_planning", raise_exception=True)
def update_event(request):
    if request.method != "POST":
        return redirect(
            reverse("planning") + build_redirect_params(extract_filters_short(request))
        )

    event_id = request.POST.get("event_id")
    new_date = request.POST.get("start")
    if not event_id or not new_date:
        messages.error(request, "Données invalides pour la mise à jour.")
        return redirect(
            reverse("planning") + build_redirect_params(extract_filters_short(request))
        )

    try:
        with transaction.atomic():
            planning = get_object_or_404(
                Planning, id=event_id, pointage_created_at__isnull=True
            )
            planning.shift_date = datetime.strptime(new_date, "%Y-%m-%d").date()
            planning.save()
            logger.info(f"Planning {event_id} déplacé à {new_date}.")
        messages.success(request, "Planning mis à jour avec succès.")
    except ValueError:
        messages.error(request, "Format de date invalide.")
    except Exception as e:
        logger.exception("Erreur lors de la mise à jour du planning: %s", e)
        messages.error(request, "Erreur lors de la mise à jour du planning.")
    return redirect(
        reverse("planning") + build_redirect_params(extract_filters_short(request))
    )


@require_POST
@permission_required("rh.supprimer_planning", raise_exception=True)
def delete_event(request, event_id=None):
    """
    Supprime un planning. event_id peut venir de l'URL (param) ou du body (POST JSON ou form).
    """
    try:
        # 1) extraire event_id depuis body si non fourni via URL
        if not event_id:
            # essayer form POST
            event_id = request.POST.get("event_id")
            if not event_id:
                # essayer JSON body
                try:
                    body = json.loads(request.body.decode("utf-8") or "{}")
                    event_id = body.get("event_id")
                except Exception:
                    event_id = None

        if not event_id:
            logger.warning("delete_event: event_id absent dans la requête")
            return json_response(False, "Paramètre event_id requis", status=400)

        # forcer int si possible (sécuriser)
        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            logger.warning("delete_event: event_id invalide: %r", event_id)
            return json_response(False, "event_id invalide", status=400)

        logger.debug(
            "delete_event: tentative suppression event_id=%s by user=%s",
            event_id,
            request.user,
        )

        planning = get_object_or_404(Planning, id=event_id, decharge__isnull=True)

        # Vérifier si validé
        if planning.pointage_created_at:
            return json_response(
                False, "❌ Impossible de supprimer un planning déjà validé", status=400
            )

        employee_name = planning.employee.nom_prenom if planning.employee else "Inconnu"
        planning_date = (
            planning.shift_date.strftime("%d/%m/%Y") if planning.shift_date else "N/A"
        )

        planning.delete()
        logger.info(
            "Planning supprimé: id=%s user=%s %s - %s",
            event_id,
            request.user,
            employee_name,
            planning_date,
        )

        return json_response(
            True,
            f"✅ Planning de {employee_name} du {planning_date} supprimé avec succès",
        )

    except Planning.DoesNotExist:
        logger.warning("delete_event: planning introuvable id=%s", event_id)
        return json_response(False, "❌ Planning non trouvé", status=404)
    except PermissionDenied:
        raise
    except Exception as e:
        logger.exception(
            "Erreur lors de la suppression du planning %s: %s", event_id, e
        )
        return json_response(
            False, f"❌ Erreur lors de la suppression: {str(e)}", status=500
        )


@permission_required("rh.exporter_planning", raise_exception=True)
def print_planning(request):
    filters = extract_filters_short(request)  # Use the short version that handles IDs
    queryset = Planning.objects.select_related(
        "employee", "service", "shift", "poste"
    ).all()

    # Update filtering to use IDs
    if filters["service_id"] != "all":
        queryset = queryset.filter(service_id=filters["service_id"])
    if filters["shift_id"] != "all":
        queryset = queryset.filter(shift_id=filters["shift_id"])
    if filters["employee_id"] != "all":
        queryset = queryset.filter(employee_id=filters["employee_id"])
    if filters["poste_id"] != "all":
        queryset = queryset.filter(poste_id=filters["poste_id"])
    if filters["start_date"]:
        try:
            start_date = datetime.strptime(filters["start_date"], "%Y-%m-%d").date()
            queryset = queryset.filter(shift_date__gte=start_date)
        except ValueError:
            pass
    if filters["end_date"]:
        try:
            end_date = datetime.strptime(filters["end_date"], "%Y-%m-%d").date()
            queryset = queryset.filter(shift_date__lte=end_date)
        except ValueError:
            pass

    queryset = queryset.order_by("shift_date")

    plannings = [
        {
            "shift_date": p.shift_date,
            "full_name": p.employee.nom_prenom,
            "shift": p.shift.label if p.shift else "",
            "service": p.service.name if p.service else "",
            "poste": p.poste.label if p.poste else "",
        }
        for p in queryset
    ]

    # Get display names for the template
    selected_service_name = "all"
    selected_shift_name = "all"
    selected_employee_name = "all"
    selected_poste_name = "all"

    if filters["service_id"] != "all":
        try:
            service = Service.objects.get(id=filters["service_id"])
            selected_service_name = service.name
        except Service.DoesNotExist:
            pass

    if filters["shift_id"] != "all":
        try:
            shift = Shift.objects.get(id=filters["shift_id"])
            selected_shift_name = shift.label
        except Shift.DoesNotExist:
            pass

    if filters["employee_id"] != "all":
        try:
            employee = Personnel.objects.get(id=filters["employee_id"])
            selected_employee_name = employee.nom_prenom
        except Personnel.DoesNotExist:
            pass

    if filters["poste_id"] != "all":
        try:
            poste = Poste.objects.get(id=filters["poste_id"])
            selected_poste_name = poste.label
        except Poste.DoesNotExist:
            pass

    rendered_html = render(
        request,
        "planning/planning_pdf.html",
        {
            "selected_service": selected_service_name,
            "selected_shift": selected_shift_name,
            "selected_employee": selected_employee_name,
            "selected_poste": selected_poste_name,
            "selected_start_date": filters["start_date"],
            "selected_end_date": filters["end_date"],
            "plannings": plannings,
        },
    ).content.decode("utf-8")

    pdf_stream = BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_stream)
    if pisa_status.err:
        logger.error("Erreur lors de la création du PDF")
        return HttpResponse("Erreur lors de la création du PDF", status=500)

    pdf_stream.seek(0)
    response = HttpResponse(pdf_stream, content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=planning.pdf"
    return response


@transaction.atomic
@login_required
def validate_presence(request, event_id=None):
    try:
        # extraire event_id depuis URL ou body
        if not event_id:
            event_id = request.POST.get("event_id")
            if not event_id:
                try:
                    body = json.loads(request.body.decode("utf-8") or "{}")
                    event_id = body.get("event_id")
                except Exception:
                    event_id = None

        if not event_id:
            logger.warning("validate_presence: event_id absent")
            return json_response(False, "Paramètre event_id requis", status=400)

        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            logger.warning("validate_presence: event_id invalide: %r", event_id)
            return json_response(False, "event_id invalide", status=400)

        logger.debug(
            "validate_presence: tentative validation event_id=%s by user=%s",
            event_id,
            request.user,
        )

        planning = get_object_or_404(Planning, id=event_id)

        if planning.pointage_created_at:
            return json_response(False, "❌ Ce planning est déjà validé", status=400)

        if planning.shift_date < date.today() - timedelta(days=7):
            return json_response(
                False,
                "⚠️ Impossible de valider un planning de plus de 7 jours",
                status=400,
            )

        # tarif
        tarif = (
            Tarif_Gardes.objects.filter(
                poste=planning.poste, service=planning.service, shift=planning.shift
            ).first()
            or Tarif_Gardes.objects.filter(
                poste=planning.poste, service=planning.service, shift__isnull=True
            ).first()
        )

        if not tarif:
            logger.warning(
                "validate_presence: aucun tarif pour planning id=%s", event_id
            )
            planning.prix = Decimal("0.00")
            # On n'utilise pas messages.* dans réponse AJAX, on renvoie via JSON
            planning.pointage_created_at = timezone.now()
            planning.pointage_created_by = request.user.personnel
            planning.save()
            return json_response(
                True, "⚠️ Présence validée mais aucun tarif configuré (prix=0)"
            )
        else:
            planning.prix = tarif.prix
            planning.pointage_created_at = timezone.now()
            planning.pointage_created_by = request.user.personnel
            planning.save()
            employee_name = (
                planning.employee.nom_prenom if planning.employee else "Inconnu"
            )
            planning_date = (
                planning.shift_date.strftime("%d/%m/%Y")
                if planning.shift_date
                else "N/A"
            )
            return json_response(
                True,
                f"✅ Présence validée pour {employee_name} le {planning_date} ({planning.prix} DA)",
            )

    except Planning.DoesNotExist:
        logger.warning("validate_presence: planning introuvable id=%s", event_id)
        return json_response(False, "❌ Planning non trouvé", status=404)
    except Exception as e:
        logger.exception("Erreur lors de la validation de présence: %s", e)
        return json_response(
            False, f"❌ Erreur lors de la validation: {str(e)}", status=500
        )


@transaction.atomic
@login_required
def validate_presence_range(request):
    if request.method != "POST":
        return json_response(False, "Méthode non autorisée", status=405)

    try:
        # 1) essayer de parser JSON body (fetch envoie JSON)
        try:
            body_raw = request.body.decode("utf-8") if request.body else ""
            data = json.loads(body_raw) if body_raw else {}
        except Exception:
            data = {}

        # 2) fallback : données POST form-encoded (au cas où)
        if not data:
            data = request.POST.dict()

        # 3) Accepter plusieurs formats :
        #    - {"daterangepicker": "YYYY-MM-DD - YYYY-MM-DD"}
        #    - {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
        date_range = data.get("daterangepicker")
        sd = data.get("start_date") or data.get("sd")
        ed = data.get("end_date") or data.get("ed")

        if date_range:
            # cas "YYYY-MM-DD - YYYY-MM-DD"
            try:
                start_str, end_str = [d.strip() for d in date_range.split(" - ", 1)]
            except Exception:
                return json_response(
                    False, "❌ Format de date invalide (daterangepicker)", status=400
                )
        elif sd and ed:
            start_str, end_str = sd.strip(), ed.strip()
        else:
            return json_response(False, "❌ Plage de dates requise", status=400)

        # parser en date
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            return json_response(
                False, "❌ Format de date invalide (YYYY-MM-DD attendu)", status=400
            )

        # validations business (mêmes que tu avais)
        if start_date > end_date:
            return json_response(
                False,
                "❌ La date de début doit être antérieure à la date de fin",
                status=400,
            )

        if end_date < date.today() - timedelta(days=60):
            return json_response(
                False,
                "⚠️ Impossible de valider des plannings de plus de 60 jours",
                status=400,
            )

        if (end_date - start_date).days > 31:
            return json_response(
                False, "❌ La plage de dates ne peut pas dépasser 31 jours", status=400
            )

        # récupérer plannings
        plannings = Planning.objects.filter(
            shift_date__range=(start_date, end_date), pointage_created_at__isnull=True
        ).select_related("employee", "service", "poste", "shift")

        if not plannings.exists():
            return json_response(
                False,
                f"ℹ️ Aucun planning à valider entre le {start_date.strftime('%d/%m/%Y')} et le {end_date.strftime('%d/%m/%Y')}",
                status=400,
            )

        validated_count = 0
        errors = []

        for planning in plannings:
            try:
                tarif = (
                    Tarif_Gardes.objects.filter(
                        poste=planning.poste,
                        service=planning.service,
                        shift=planning.shift,
                    ).first()
                    or Tarif_Gardes.objects.filter(
                        poste=planning.poste,
                        service=planning.service,
                        shift__isnull=True,
                    ).first()
                )
                print(f"Tarif trouvé: {tarif.prix if tarif else 'Aucun tarif'} pour {planning.employee.nom_prenom} le {planning.shift_date.strftime('%d/%m/%Y')}")

                planning.prix = tarif.prix if tarif else Decimal("0.00")
                planning.pointage_created_at = timezone.now()
                planning.pointage_created_by = request.user.personnel
                planning.save()
                validated_count += 1

                if not tarif:
                    errors.append(
                        f"⚠️ Aucun tarif pour {planning.employee.nom_prenom} le {planning.shift_date.strftime('%d/%m/%Y')}"
                    )

            except Exception as e:
                errors.append(
                    f"❌ Erreur pour {planning.employee.nom_prenom} le {planning.shift_date.strftime('%d/%m/%Y')}: {str(e)}"
                )
                logger.exception(
                    f"Erreur lors de la validation du planning {planning.id}: %s", e
                )

        message = f"✅ {validated_count} pointages validés avec succès"
        if errors:
            message += f". {len(errors)} erreurs/avertissements:"
            for error in errors[:5]:
                message += f"\n• {error}"
            if len(errors) > 5:
                message += f"\n• ... et {len(errors) - 5} autres erreurs"

        logger.info(
            f"Validation en lot: {validated_count} plannings validés, {len(errors)} erreurs"
        )
        return json_response(True, message)

    except json.JSONDecodeError:
        return json_response(False, "❌ Données JSON invalides", status=400)
    except Exception as e:
        logger.exception("Erreur lors de la validation multiple de présence: %s", e)
        return json_response(False, f"❌ Erreur inattendue: {str(e)}", status=500)


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def get_honoraires_acte(request):
    poste_id = request.GET.get("id_poste")
    if not poste_id:
        return json_response(False, "❌ Paramètre poste_id requis", status=400)

    try:
        # Vérifier que le poste existe
        poste = get_object_or_404(Poste, id=poste_id)

        actes = HonorairesActe.objects.filter(poste_id=poste_id).order_by("name_acte")

        if not actes.exists():
            return json_response(
                False, f"ℹ️ Aucun acte configuré pour le poste {poste.label}", status=404
            )

        actes_list = [
            {"id_acte": a.id, "name_acte": a.name_acte, "prix_acte": str(a.prix_acte)}
            for a in actes
        ]

        return json_response(
            True, f"✅ {len(actes_list)} actes trouvés pour {poste.label}", actes_list
        )

    except Poste.DoesNotExist:
        return json_response(False, "❌ Poste non trouvé", status=404)
    except Exception as e:
        logger.exception("Erreur récupération actes pour poste %s: %s", poste_id, e)
        return json_response(
            False, f"❌ Erreur lors de la récupération: {str(e)}", status=500
        )


@transaction.atomic
@login_required
def add_pointage_acte(request):
    if request.method != "POST":
        return json_response(False, "Méthode non autorisée", status=405)

    try:
        data = json.loads(request.body)
        event_id, acte_id, nbr_actes = (
            data.get("event_id"),
            data.get("acte_id"),
            data.get("nbr_actes"),
        )

        if not all([event_id, acte_id, nbr_actes]):
            return json_response(
                False,
                "❌ Données incomplètes (event_id, acte_id, nbr_actes requis)",
                status=400,
            )

        # Validation du nombre d'actes
        try:
            nbr_actes = int(nbr_actes)
            if nbr_actes <= 0:
                return json_response(
                    False, "❌ Le nombre d'actes doit être positif", status=400
                )
            if nbr_actes > 100:  # Limite raisonnable
                return json_response(
                    False, "❌ Le nombre d'actes ne peut pas dépasser 100", status=400
                )
        except ValueError:
            return json_response(
                False, "❌ Le nombre d'actes doit être un entier valide", status=400
            )

        # Vérification de l'existence des objets
        planning = get_object_or_404(Planning, id=event_id)
        acte = get_object_or_404(HonorairesActe, id=acte_id)

        # Vérifier que l'acte correspond au poste du planning
        if acte.poste_id != planning.poste_id:
            return json_response(
                False,
                "❌ Cet acte n'est pas compatible avec le poste du planning",
                status=400,
            )

        # Vérifier que le planning est validé
        if not planning.pointage_created_at:
            return json_response(
                False,
                "❌ Le planning doit être validé avant d'ajouter des actes",
                status=400,
            )

        # Créer ou mettre à jour le pointage d'acte
        pointage_acte, created = PointagesActes.objects.update_or_create(
            planning=planning, acte=acte, defaults={"nbr_actes": nbr_actes}
        )

        # Recalculer le prix total des actes pour ce planning
        total_price = sum(
            pa.acte.prix_acte * pa.nbr_actes
            for pa in planning.pointages_actes.all()
            if pa.acte
        )

        planning.prix_acte = total_price
        planning.save(update_fields=["prix_acte"])

        employee_name = planning.employee.nom_prenom
        planning_date = planning.shift_date.strftime("%d/%m/%Y")
        acte_total = acte.prix_acte * nbr_actes

        action = "ajouté" if created else "mis à jour"

        logger.info(
            f"Pointage acte {action} pour planning {event_id}: {employee_name} - {acte.name_acte} x{nbr_actes} = {acte_total} DA"
        )

        message = f"✅ Acte {action}: {acte.name_acte} x{nbr_actes} = {acte_total} DA pour {employee_name} le {planning_date}"

        return json_response(
            True,
            message,
            {
                "total_price": str(total_price),
                "acte_total": str(acte_total),
                "created": created,
            },
        )

    except json.JSONDecodeError:
        return json_response(False, "❌ Données JSON invalides", status=400)
    except Planning.DoesNotExist:
        return json_response(False, "❌ Planning non trouvé", status=404)
    except HonorairesActe.DoesNotExist:
        return json_response(False, "❌ Acte non trouvé", status=404)
    except Exception as e:
        logger.exception("Erreur lors de l'ajout du pointage acte: %s", e)
        return json_response(
            False, f"❌ Erreur lors de l'enregistrement: {str(e)}", status=500
        )
