# medecin/decorators.py
from functools import wraps
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404
from .models import Medecin


def medecin_required(view_func):
    """
    Décorateur pour vérifier l'existence d'un médecin
    """

    @wraps(view_func)
    def wrapper(request, medecin_id, *args, **kwargs):
        medecin = get_object_or_404(Medecin, id=medecin_id)
        return view_func(request, medecin_id, medecin=medecin, *args, **kwargs)

    return wrapper


def ajax_required(view_func):
    """
    Décorateur pour les vues AJAX
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": "Cette requête doit être AJAX"}, status=400)
        return view_func(request, *args, **kwargs)

    return wrapper
