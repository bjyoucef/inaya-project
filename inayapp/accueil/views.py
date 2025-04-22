import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@require_POST
@login_required
def update_theme(request):
    try:
        data = json.loads(request.body)
        theme = data.get("theme")

        if theme not in ["light", "dark"]:
            return JsonResponse(
                {"status": "error", "message": "Valeur de thème invalide"}, status=400
            )

        # Mise à jour du thème
        theme_obj = request.user.theme
        theme_obj.theme = theme
        theme_obj.save()

        return JsonResponse({"status": "success", "theme": theme})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


def home(request):
    # On récupère les messages pour les afficher dans le template
    msg_list = list(messages.get_messages(request))
    for msg in msg_list:
        if "success" in msg.tags:
            msg.bg_color = "linear-gradient(to right, #00b09b, #96c93d)"
        else:
            msg.bg_color = "linear-gradient(to right, #f85032, #e73827)"
    return render(request, 'home.html', {'messages': msg_list})
