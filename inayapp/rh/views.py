# views.py
from calendar import c
from collections import defaultdict
import logging
from datetime import date, datetime, time, timedelta
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import permission_required, login_required
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404, reverse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
from xhtml2pdf import pisa
from django.utils import timezone
from django.views.generic import ListView
from .models import Employee, Attendance, Personnel, Services, Planning
from django.views.decorators.csrf import csrf_exempt
from accueil.models import ConfigDate

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_events(request):
    """
    Retourne les événements sous forme JSON pour un chargement asynchrone.
    """
    try:
        allowed_services = [
            s.service_name
            for s in Services.objects.all()
            if request.user.has_perm(f"rh.view_service_{s.service_name}")
        ]
        qs = Planning.objects.filter(
            employee=request.GET.get("employee"),
            id_service__service_name__in=allowed_services,
            shift_type=request.GET.get("shift"),
            shift_date__range=[request.GET.get("start"), request.GET.get("end")],
        ).select_related("employee", "id_service")
        events = [
            {
                "id": event.id,
                "title": f"{event.employee} - {event.shift_type}",
                "start": event.shift_date.isoformat(),
                "color": event.id_service.color,
                "extendedProps": {"time": event.get_time_display()},
            }
            for event in qs.iterator()
        ]
        return JsonResponse({"events": events})
    except Exception as e:
        logger.exception("Erreur lors du chargement asynchrone des événements")
        return JsonResponse(
            {"events": [], "error": "Erreur lors du chargement"}, status=500
        )


def extract_filters(request):
    """
    Extrait les filtres de la requête et retourne un dictionnaire avec des valeurs par défaut.
    """
    return {
        "service": request.GET.get("service", "all"),
        "employee": request.GET.get("employee", "all"),
        "shift": request.GET.get("shift", "all"),
        "start_date": request.GET.get("start_date", ""),
        "end_date": request.GET.get("end_date", ""),
    }


def build_redirect_params(filters):
    """
    Construit les paramètres de redirection à partir des filtres.
    """
    return (
        f"?service={filters['service']}&shift={filters['shift']}"
        f"&employee={filters['employee']}&start_date={filters['start_date']}"
        f"&end_date={filters['end_date']}"
    )


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def planning(request):
    filters = extract_filters(request)

    # Configuration et mise à jour des dates utilisateur
    config, _ = ConfigDate.objects.get_or_create(
        user=request.user,
        page="planning",
        defaults={"start_date": "2025-01-01", "end_date": "2025-01-01"},
    )
    if filters["start_date"]:
        config.start_date = filters["start_date"]
    if filters["end_date"]:
        config.end_date = filters["end_date"]
    config.save()

    start_date = filters["start_date"] or config.start_date
    end_date = filters["end_date"] or config.end_date

    # Conversion en ISO si nécessaire
    filters["start_date"] = (
        start_date.isoformat() if isinstance(start_date, date) else start_date
    )
    filters["end_date"] = (
        end_date.isoformat() if isinstance(end_date, date) else end_date
    )

    # Construction du filtre de requête
    planning_filter = Q(shift_date__range=[filters["start_date"], filters["end_date"]])
    if filters["service"] != "all":
        planning_filter &= Q(id_service__service_name=filters["service"])
    if filters["employee"] != "all":
        # Recherche sur le champ unique nom_prenom
        employee_name = filters["employee"].strip()
        planning_filter &= Q(employee__nom_prenom__icontains=employee_name)
    if filters["shift"] != "all":
        planning_filter &= Q(shift_type=filters["shift"])

    try:
        plannings = Planning.objects.filter(planning_filter)
    except Exception:
        logger.exception("Erreur lors du filtrage des plannings")
        plannings = []

    # Récupération des services autorisés et des employés actifs
    services = [
        s
        for s in Services.objects.all()
        if request.user.has_perm(f"rh.view_service_{s.service_name}")
    ]
    employees = Personnel.objects.filter(statut_activite=1, use_in_planning=1).order_by(
        "nom_prenom"
    )

    # Préparation des événements pour le calendrier
    service_colors = {s.service_name: s.color for s in services}
    shift_configs = {
        "day": (timedelta(hours=8), timedelta(hours=8)),
        "night": (timedelta(hours=17), timedelta(hours=16)),
        "24H": (timedelta(hours=8), timedelta(hours=24)),
    }
    events = []
    for p in plannings.iterator():
        time_config = shift_configs.get(p.shift_type)
        if time_config and all(time_config):
            event_start = (
                datetime.combine(p.shift_date, datetime.min.time()) + time_config[0]
            )
            event_end = event_start + time_config[1]
            events.append(
                {
                    "id": p.id,
                    "title": f"{p.employee} - {p.shift_type} - {p.id_service.service_name}",
                    "start": event_start.isoformat(),
                    "end": event_end.isoformat(),
                    "backgroundColor": service_colors.get(
                        p.id_service.service_name, "gray"
                    ),
                    "borderColor": service_colors.get(
                        p.id_service.service_name, "gray"
                    ),
                }
            )

    context = {
        "employees": employees,
        "services": services,
        "events": events,
        "selected": filters,
        "title": "Plannings",
        "user": request.user,
    }
    return render(request, "rh/planning.html", context)


@permission_required("rh.creer_planning", raise_exception=True)
def save_planning(request):
    # Extraction centralisée des filtres (GET ou POST)
    filters = (
        {
            "service": request.POST.get("service", "all"),
            "employee": request.POST.get("employee", "all"),
            "shift": request.POST.get("shift", "all"),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
        }
        if request.method == "POST"
        else extract_filters(request)
    )

    print("filters:", filters)

    redirect_params = build_redirect_params(filters)
    if request.method != "POST":
        return redirect(reverse("planning") + redirect_params)

    # Récupération et validation des données du formulaire
    service_name = request.POST.get("service")
    employee_full_name = request.POST.get("employee")
    shift_type = request.POST.get("shift")
    shift_date_str = request.POST.get("date")
    event_id = request.POST.get("event_id")

    if not all([service_name, employee_full_name, shift_type, shift_date_str]):
        messages.error(request, "Tous les champs sont obligatoires.")
        return redirect(reverse("planning") + redirect_params)

    try:
        shift_date = datetime.strptime(shift_date_str, "%Y-%m-%d").date()
    except ValueError:
        messages.error(
            request, "Date invalide. Veuillez utiliser le format AAAA-MM-JJ."
        )
        return redirect(reverse("planning") + redirect_params)

    try:
        with transaction.atomic():
            # Récupération du service
            service_obj = get_object_or_404(Services, service_name=service_name)
            # Recherche de l'employé via le champ unique nom_prenom
            employee_obj = Personnel.objects.filter(
                nom_prenom__iexact=employee_full_name
            ).first()
            if not employee_obj:
                messages.error(request, "Employé introuvable.")
                return redirect(reverse("planning") + redirect_params)

            if event_id:
                planning_obj = Planning.objects.filter(id=event_id).first()
                if planning_obj:
                    planning_obj.id_service = service_obj
                    planning_obj.shift_date = shift_date
                    planning_obj.shift_type = shift_type
                    planning_obj.employee = employee_obj
                    planning_obj.save()
                    logger.info(f"Mise à jour du planning (ID {event_id}) réussie.")
                else:
                    messages.error(request, "Événement non trouvé pour mise à jour.")
                    return redirect(reverse("planning") + redirect_params)
            else:
                Planning.objects.create(
                    id_service=service_obj,
                    shift_date=shift_date,
                    shift_type=shift_type,
                    employee=employee_obj,
                    # Correction : assigner l'objet Personnel associé à l'utilisateur
                    id_created_par=request.user.personnel,
                    created_at=now(),
                )
                logger.info("Création d'un nouveau planning réussie.")
    except Exception as e:
        logger.exception("Erreur lors de l'enregistrement du planning")
        messages.error(request, "Erreur lors de l'enregistrement du planning.")
        return redirect(reverse("planning") + redirect_params)

    messages.success(request, "Planning enregistré avec succès.")
    return redirect(reverse("planning") + redirect_params)


@permission_required("rh.modifier_planning", raise_exception=True)
def update_event(request):
    """
    Mise à jour d’un événement via déplacement sur le calendrier.
    """
    if request.method != "POST":
        return redirect(reverse("planning"))

    selected_params = build_redirect_params(
        {
            "service": request.POST.get("service", "all"),
            "employee": request.POST.get("employee", "all"),
            "shift": request.POST.get("shift", "all"),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
        }
    )
    event_id = request.POST.get("event_id")
    new_date = request.POST.get("start")
    if not event_id or not new_date:
        return redirect(reverse("planning") + selected_params)
    try:
        with transaction.atomic():
            planning_obj = Planning.objects.filter(id=event_id).first()
            if planning_obj:
                planning_obj.shift_date = new_date
                planning_obj.save()
    except Exception:
        logger.exception("Erreur lors de la mise à jour du planning")
    return redirect(reverse("planning") + selected_params)


@permission_required("rh.supprimer_planning", raise_exception=True)
def delete_event(request, event_id):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"},
            status=405,
            json_dumps_params={"ensure_ascii": False},
        )
    try:
        event = Planning.objects.filter(id=event_id).first()
        if not event:
            return JsonResponse(
                {"success": False, "message": "Événement introuvable"},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )
        event.delete()
        return JsonResponse(
            {"success": True, "message": "Événement supprimé"},
            status=200,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.exception("Erreur suppression")
        return JsonResponse(
            {"success": False, "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@permission_required("rh.exporter_planning", raise_exception=True)
def print_planning(request):
    """
    Export du planning au format PDF avec nettoyage de ressources via BytesIO.
    """
    selected_service = request.GET.get("service", "all")
    selected_shift = request.GET.get("shift", "all")
    selected_employee = request.GET.get("employee", "all")
    selected_start_date = request.GET.get("start_date", "")
    selected_end_date = request.GET.get("end_date", "")

    # Recherche de l'employé si filtré
    employee_obj = None
    if selected_employee != "all":
        employee_obj = Personnel.objects.filter(
            nom_prenom__iexact=selected_employee
        ).first()
        if employee_obj is None:
            return redirect(
                reverse("planning") + "?message=Employé+introuvable.&category=danger"
            )
    # Recherche du service si filtré
    service_obj = None
    if selected_service != "all":
        service_obj = Services.objects.filter(service_name=selected_service).first()

    queryset = Planning.objects.select_related("employee", "id_service").all()
    if service_obj:
        queryset = queryset.filter(id_service=service_obj)
    if selected_shift != "all":
        queryset = queryset.filter(shift_type=selected_shift)
    if employee_obj:
        queryset = queryset.filter(employee=employee_obj)
    if selected_start_date:
        queryset = queryset.filter(shift_date__gte=selected_start_date)
    if selected_end_date:
        queryset = queryset.filter(shift_date__lte=selected_end_date)
    queryset = queryset.order_by("shift_date")

    plannings = [
        {
            "shift_date": p.shift_date,
            "full_name": p.employee.nom_prenom,
            "shift_type": p.shift_type,
            "service": p.id_service.service_name if p.id_service else "",
        }
        for p in queryset.iterator()
    ]
    rendered_html = render(
        request,
        "rh/planning_pdf.html",
        {
            "selected_service": selected_service,
            "selected_shift": selected_shift,
            "selected_employee": selected_employee,
            "selected_start_date": selected_start_date,
            "selected_end_date": selected_end_date,
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
def validate_presence(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Méthode non autorisée"}, status=405
        )
    try:
        planning_id = request.POST.get("planning_id")
        planning = Planning.objects.get(pk=planning_id)
        planning.pointage_created_at = now()
        planning.pointage_id_created_par = (
            request.user.personnel
        )  # Assurez-vous que request.user est lié à un Personnel
        planning.save()
        return JsonResponse(
            {"success": True, "message": "Présence validée avec succès."}
        )
    except Planning.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Planning introuvable."}, status=404
        )
    except Exception as e:
        logger.exception("Erreur lors de la validation de présence")
        return JsonResponse({"success": False, "message": str(e)}, status=500)

# views.py
from .models import Employee, Attendance


from django.shortcuts import render
from django.utils import timezone


from collections import defaultdict
from datetime import datetime, timedelta, date, time
from django.views.generic import ListView
from django.db.models import Q


class attendance_report(ListView):
    model = Attendance
    template_name = "rh/attendance_report.html"
    context_object_name = "report_data"

    def get_date_range(self, config):
        """Retourne la plage de dates validée."""
        start_date = config.start_date
        end_date = config.end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return start_date, end_date

    def get_queryset(self):
        employee_id = self.request.GET.get("employee")
        # Récupération ou création de la configuration de dates pour l'utilisateur
        config, _ = ConfigDate.objects.get_or_create(
            user=self.request.user,
            page="pointage",
            defaults={"start_date": date.today(), "end_date": date.today()},
        )
        # Mise à jour de la config selon les paramètres GET
        for param in ["start_date", "end_date"]:
            value = self.request.GET.get(param)
            if value:
                try:
                    setattr(config, param, datetime.strptime(value, "%Y-%m-%d").date())
                except ValueError:
                    pass
        config.save()
        start_date, end_date = self.get_date_range(config)
        # On élargit la plage pour prendre en compte les chevauchements (ex : shifts de nuit)
        qs = (
            Attendance.objects.filter(
                check_time__date__gte=start_date - timedelta(days=1),
                check_time__date__lte=end_date + timedelta(days=1),
            )
            .select_related("employee")
            .order_by("-check_time")
        )
        if employee_id:
            qs = qs.filter(employee__anviz_id=employee_id)
        return qs

    def calculate_working_hours(self, attendances, employee, start_date, end_date):
        """
        Calcule les heures travaillées pour un employé sur une plage de dates.
        Pour chaque groupe de pointages (regroupé par date effective), la paire est déterminée
        en prenant le premier enregistrement comme entrée et le dernier comme sortie.
        Pour un shift de nuit, si un jour (effective) n'a qu'un seul enregistrement et le jour suivant
        aussi, ils sont combinés pour constituer l'entrée et la sortie.
        """
        from collections import defaultdict
        from datetime import timedelta, datetime
        from django.utils import timezone

        tz = timezone.get_current_timezone()

        # Horaires de référence (par défaut si non renseigné)
        reference_start = employee.reference_start or time(8, 0)
        reference_end = employee.reference_end or time(16, 0)
        # Pour les shifts de nuit, on s'assure d'utiliser le champ shift
        is_night_shift = (employee.shift == "night") or (reference_end < reference_start)

        # On ne conserve que les enregistrements « IN » (puisqu'il n'y a pas de OUT dans la base)
        # Note : dans votre cas, même si plusieurs enregistrements sont de type "IN", on va en déduire
        # la paire en considérant que le premier correspond à l'entrée et le dernier à la sortie.
        in_records = [att for att in attendances if att.check_type == "IN"]

        # Regroupement par "date effective"
        # Pour le shift de nuit, les enregistrements antérieurs à reference_end sont rattachés à la veille.
        groups = defaultdict(list)
        for att in in_records:
            att_time = att.check_time.time()
            att_date = att.check_time.date()
            effective_date = (
                att_date - timedelta(days=1)
                if is_night_shift and att_time < reference_end
                else att_date
            )
            groups[effective_date].append(att)

        # Pour chaque groupe, trier par check_time
        grouped = {
            d: sorted(records, key=lambda a: a.check_time)
            for d, records in groups.items()
            if start_date <= d <= end_date
        }

        results = []
        processed_dates = set()

        if is_night_shift:
            # Pour un shift de nuit, il peut arriver que la paire se répartisse sur deux jours effectifs
            # Exemple : le 2024-11-23 on a un seul enregistrement à 19:11:58 et le 2024-11-24 un seul enregistrement à 08:14:34.
            # On va itérer sur les dates effectives triées et, si la date D et la date D+1 ont chacune un seul enregistrement,
            # les combiner.
            sorted_dates = sorted(grouped.keys())
            i = 0
            while i < len(sorted_dates):
                d = sorted_dates[i]
                if d in processed_dates:
                    i += 1
                    continue
                recs = grouped[d]
                if len(recs) >= 2:
                    # Plusieurs pointages : on prend le premier comme IN, le dernier comme OUT.
                    in_time = recs[0].check_time
                    out_time = recs[-1].check_time
                    processed_dates.add(d)
                else:
                    # Un seul enregistrement sur cette date
                    # Vérifier si la date suivante existe et a aussi un seul enregistrement
                    if i + 1 < len(sorted_dates):
                        d_next = sorted_dates[i + 1]
                        recs_next = grouped[d_next]
                        if len(recs_next) == 1:
                            # On combine : le pointage de d sera considéré comme IN, celui de d_next comme OUT.
                            in_time = recs[0].check_time
                            out_time = recs_next[0].check_time
                            processed_dates.add(d)
                            processed_dates.add(d_next)
                            i += 1  # On saute le jour suivant
                        else:
                            # Sinon, on ne peut former de paire complète : on prend le seul enregistrement comme les deux.
                            in_time = out_time = recs[0].check_time
                            processed_dates.add(d)
                    else:
                        in_time = out_time = recs[0].check_time
                        processed_dates.add(d)

                # Création des horaires théoriques pour la journée effective d'entrée
                # Pour le shift de nuit, le scheduled_end est calculé sur le jour suivant.
                scheduled_start = timezone.make_aware(
                    datetime.combine(d, reference_start), tz
                )
                if is_night_shift:
                    scheduled_end = timezone.make_aware(
                        datetime.combine(d + timedelta(days=1), reference_end), tz
                    )
                else:
                    scheduled_end = timezone.make_aware(
                        datetime.combine(d, reference_end), tz
                    )

                # Assurer que les in_time et out_time soient aware (sinon, on les convertit)
                if timezone.is_naive(in_time):
                    in_time = timezone.make_aware(in_time, tz)
                if timezone.is_naive(out_time):
                    out_time = timezone.make_aware(out_time, tz)

                total_work = out_time - in_time

                # Calcul du retard et des heures supplémentaires
                late_delta = in_time - scheduled_start
                # Tolérance de 5 minutes
                late_minutes = max(late_delta.total_seconds() / 60 - 5, 0)
                overtime = max(
                    out_time - scheduled_end, timedelta()
                )  # Si out_time > scheduled_end

                results.append(
                    {
                        "date": d,  # La date effective de l'entrée
                        "pairs": [(in_time, out_time)],
                        "total": total_work,
                        "overtime": overtime,
                        "late_minutes": int(late_minutes),
                        "late": late_minutes > 0,
                        "entries": [in_time, out_time],
                    }
                )
                i += 1
        else:
            # Pour un shift de jour
            for d, recs in grouped.items():
                if len(recs) >= 2:
                    in_time = recs[0].check_time
                    out_time = recs[-1].check_time
                else:
                    # Si un seul enregistrement, on le considère comme les deux (ce qui donnera 0 durée)
                    in_time = out_time = recs[0].check_time

                # Horaires théoriques pour la journée
                scheduled_start = timezone.make_aware(
                    datetime.combine(d, reference_start), tz
                )
                scheduled_end = timezone.make_aware(datetime.combine(d, reference_end), tz)

                if timezone.is_naive(in_time):
                    in_time = timezone.make_aware(in_time, tz)
                if timezone.is_naive(out_time):
                    out_time = timezone.make_aware(out_time, tz)

                total_work = out_time - in_time
                late_delta = in_time - scheduled_start
                late_minutes = max(late_delta.total_seconds() / 60 - 5, 0)
                overtime = max(out_time - scheduled_end, timedelta())

                results.append(
                    {
                        "date": d,
                        "pairs": [(in_time, out_time)],
                        "total": total_work,
                        "overtime": overtime,
                        "late_minutes": int(late_minutes),
                        "late": late_minutes > 0,
                        "entries": [in_time, out_time],
                    }
                )

        return sorted(results, key=lambda x: x["date"], reverse=True)

    def calculate_totals(self, days):
        totals = {
            "total_work": timedelta(),
            "total_overtime": timedelta(),
            "total_late": 0,
            "work_days": set(),
        }
        for day in days:
            totals["total_work"] += day["total"]
            totals["total_overtime"] += day["overtime"]
            totals["total_late"] += day["late_minutes"]
            totals["work_days"].add(day["date"])
        return totals

    def get_work_days(self, start, end):
        """Retourne l'ensemble des jours ouvrés (hors week-end) dans l'intervalle."""
        return {
            start + timedelta(days=i)
            for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = ConfigDate.objects.get(user=self.request.user, page="pointage")

        # Si end_date n'est pas défini, on le force à start_date ou à la date d'aujourd'hui
        if not config.end_date:
            config.end_date = config.start_date or date.today()
            config.save()
        start_date, end_date = self.get_date_range(config)
        work_days = self.get_work_days(start_date, end_date)

        # Récupère les employés présents dans le queryset (afin d'éviter les doublons)
        employee_ids = self.get_queryset().values_list("employee", flat=True).distinct()
        employees = Employee.objects.filter(id__in=employee_ids).prefetch_related(
            "attendances"
        )
        report = []
        for employee in employees:
            # On travaille sur tous les pointages de l'employé dans la plage demandée
            days = self.calculate_working_hours(
                employee.attendances.all(), employee, start_date, end_date
            )
            totals = self.calculate_totals(days)
            report.append(
                {
                    "employee": employee,
                    "days": days,
                    "totals": {
                        "hours": totals["total_work"],
                        "overtime": totals["total_overtime"],
                        "late": totals["total_late"],
                        "absence": len(work_days - totals["work_days"]),
                    },
                }
            )
        context.update(
            {
                "report": report,
                "config": config,
                "date_range": f"{start_date} - {end_date}",
                "employees": Employee.objects.all(),  # Pour alimenter le sélecteur dans le template
            }
        )
        return context


@csrf_exempt
def save_reference_hours(request):
    if request.method == "POST":
        emp_id = request.POST.get("employee_id")
        reference_start = request.POST.get("reference_start")
        reference_end = request.POST.get("reference_end")

        try:
            employee = Employee.objects.get(id=emp_id)
            employee.reference_start = reference_start
            employee.reference_end = reference_end
            employee.save()
            return redirect(reverse("attendance_report"))

        except Employee.DoesNotExist:
            return HttpResponse("Employé introuvable", status=404)

    return HttpResponse("Méthode non autorisée", status=405)


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.management import call_command

@require_POST
def sync_attendances(request):

    try:
        # Appeler votre commande de synchronisation
        call_command("sync_attendances")
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def sync_users(request):

    try:
        # Appeler votre commande de synchronisation
        call_command("sync_user")
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
