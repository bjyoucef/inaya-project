from django.shortcuts import render

from datetime import timedelta
from django.views.generic import TemplateView
from django.http import JsonResponse

from inayapp.medical.models.rendez_vous import RendezVous


class CalendarView(TemplateView):
    template_name = "medical/calendar.html"


def rendezvous_json(request):
    events = RendezVous.objects.select_related("patient", "medecin", "service").filter(
        statut__in=["PLANIFIE", "CONFIRME"]
    )

    data = [
        {
            "id": rdv.id,
            "title": f"{rdv.patient} - {rdv.medecin.nom_complet}",
            "start": rdv.date_heure.isoformat(),
            "end": (rdv.date_heure + timedelta(minutes=rdv.duree)).isoformat(),
            "color": rdv.service.color if rdv.service else "#3788d8",
            "extendedProps": {
                "motif": rdv.motif,
                "statut": rdv.get_statut_display(),
                "medecin": rdv.medecin.nom_complet,
                "patient": str(rdv.patient),
                "notes": rdv.notes,
            },
        }
        for rdv in events
    ]

    return JsonResponse(data, safe=False)
