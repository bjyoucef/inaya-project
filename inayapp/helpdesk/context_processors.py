# accueil/context_processors.py
from .models import Helpdesk
from django.db.models import Q

def notification(request):
    user = request.user
    id_personnel = user.id

    # On définit une condition pour les demandes non terminées (time_terminee est NULL)
    # et qui appartiennent à l'utilisateur (name == id_personnel)
    condition = Q(name=id_personnel) & Q(time_terminee__isnull=True)
    
    # Si l'utilisateur a la permission d'accéder au département IT, on ajoute aussi les demandes de type 'it'
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_IT'):
        condition |= Q(type='it') & Q(time_terminee__isnull=True)
    # Pour le département technique
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE'):
        condition |= Q(type='tech') & Q(time_terminee__isnull=True)
    # Pour le département approvisionnement
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
        condition |= Q(type='appro') & Q(time_terminee__isnull=True)
        
    demandes = Helpdesk.objects.filter(condition)
    nembre_notification = demandes.count()
    print(nembre_notification)
    return {'nembre_notification': nembre_notification}