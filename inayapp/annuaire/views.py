from django.shortcuts import render
from .models import Contacts


def index(request):
    user = request.user
    # User not logged in: show only contacts with status_phone True.
    contacts = Contacts.objects.filter(statut_activite=True)
    
    context = {
        'contacts': contacts,
        'title': 'Contacts',
        'user': user,
    }
    return render(request, 'annuaire/index.html', context)