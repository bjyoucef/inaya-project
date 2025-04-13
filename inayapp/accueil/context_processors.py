# accueil/context_processors.py
from .models import MenuItems
from helpdesk.models import Helpdesk
from django.db.models import Q



def menu_items(request):
    # Récupération de tous les éléments de menu triés
    items = MenuItems.objects.all().order_by('n')
    # Liste qui contiendra les éléments filtrés
    filtered_items = []
    
    for item in items:
        if item.permission:
            # Si une permission est définie, on vérifie que l'utilisateur la possède
            if request.user.has_perm(item.permission):
                filtered_items.append(item)
        else:
            # Si aucune permission n'est définie, on affiche l'élément par défaut
            filtered_items.append(item)
    
    return {'menu_items': filtered_items}

