from django.shortcuts import render
from django.contrib import messages

def home(request):
    # On récupère les messages pour les afficher dans le template
    msg_list = list(messages.get_messages(request))
    for msg in msg_list:
        if "success" in msg.tags:
            msg.bg_color = "linear-gradient(to right, #00b09b, #96c93d)"
        else:
            msg.bg_color = "linear-gradient(to right, #f85032, #e73827)"
    return render(request, 'layout.html', {'messages': msg_list})

