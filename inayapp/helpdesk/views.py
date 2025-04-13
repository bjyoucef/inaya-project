# helpdesk/views.py
import os
import datetime
import base64

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import Helpdesk
from django.contrib.auth.decorators import permission_required,login_required
from django.db.models import Q
from django.utils import timezone

# Fonctions utilitaires pour la sauvegarde
def save_files(files, directory):
    """Sauvegarde des fichiers dans le répertoire spécifié"""
    file_paths = []
    try:
        for file in files:
            if file.name:
                # Création du chemin relatif
                file_path = os.path.join(directory, file.name)
                # Sauvegarde avec gestion automatique des doublons
                saved_path = default_storage.save(file_path, file)
                file_paths.append(saved_path)
        return ','.join(file_paths) if file_paths else None
    except Exception as e:
        print(f"Erreur sauvegarde fichiers: {e}")
        return None

def save_audio(audio_data, directory):
    """Sauvegarde des enregistrements audio au format WAV"""
    try:
        if not audio_data:
            return None
            
        # Décodage des données base64
        audio_binary = base64.b64decode(audio_data.split(',')[1])
        
        # Création du nom de fichier
        filename = f"audio_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.wav"
        file_path = os.path.join(directory, filename)
        
        # Sauvegarde du fichier
        saved_path = default_storage.save(file_path, ContentFile(audio_binary))
        return saved_path
    except Exception as e:
        print(f"Erreur sauvegarde audio: {e}")
        return None

def demande_assistance(request):
    services_list = [
        {
            'title': 'Assistance Informatiques',
            'description': 'Vous rencontrez des problèmes avec votre ordinateur, votre réseau ou vos logiciels ?',
            'icon': 'images/service-01.png',
            'modal': 'assistanceInformatiqueModal'
        },
        {
            'title': "Demande d'Approvisionnement",
            'description': 'Besoin de matériel ou de fournitures supplémentaires ?',
            'icon': 'images/service-02.png',
            'modal': 'demandeApprovisionnementModal'
        },
        {
            'title': 'Assistance Technique',
            'description': "Que ce soit pour des équipements défectueux ou toute autre difficulté technique.",
            'icon': 'images/service-03.png',
            'modal': 'assistanceTechniqueModal'
        }
    ]
    context = {
        'title': "Assistance",
        'user': request.user,
        'services_list': services_list
    }
    return render(request, 'helpdesk/demande_assistance.html', context)

# Fonction générique pour traiter la demande
def traiter_demande(request, demande_type):
    if request.method != 'POST':
        return redirect('demande_assistance')

    # Récupération des données
    ip_address = request.META.get('REMOTE_ADDR', '')
    name = request.POST.get('name')
    demande_details = request.POST.get('demande_details')
    audio_data = request.POST.get('audioData')
    files = request.FILES.getlist('file_upload')

    # Validation des champs obligatoires
    if not name or not demande_details:
        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
        return redirect('demande_assistance')

    # Création des répertoires
    file_directory = os.path.join(demande_type, 'documents')
    audio_directory = os.path.join(demande_type, 'audios')

    # Sauvegarde des fichiers
    file_paths_str = save_files(files, file_directory) if files else None

    # Sauvegarde de l'audio
    audio_path = save_audio(audio_data, audio_directory) if audio_data else None

    # Gestion des erreurs de sauvegarde
    if files and not file_paths_str:
        messages.error(request, "Erreur lors de la sauvegarde des fichiers.")
        return redirect('demande_assistance')
    
    if audio_data and not audio_path:
        messages.error(request, "Erreur lors de la sauvegarde de l'enregistrement audio.")
        return redirect('demande_assistance')

    # Enregistrement en base de données
    try:
        Helpdesk.objects.create(
            ip_address=ip_address,
            name=name,
            type=demande_type,
            details=demande_details,
            file_path=file_paths_str,
            audio_path=audio_path,
            time_send=datetime.datetime.now()
        )
        messages.success(request, "Demande envoyée avec succès!")
    except Exception as e:
        messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")

    return redirect('demande_assistance')

# Vues spécifiques selon le type de demande
def envoyer_demandeIt(request):
    return traiter_demande(request, 'it')

def envoyer_demandeTech(request):
    return traiter_demande(request, 'tech')

def envoyer_demandeAppro(request):
    return traiter_demande(request, 'appro')




@permission_required('accueil.view_menu_items_dashboard', raise_exception=True)
@login_required
def dashboard(request):
    user = request.user
    id_personnel = user.id

    # Calcul des permissions dans la vue
    has_dept_perm = (
        request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_IT") or
        request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE") or
        request.user.has_perm("helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT")
    )

    # Importer Q pour construire la condition de filtrage
    condition = Q(name=id_personnel)
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_IT'):
        condition |= Q(type='it')
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE'):
        condition |= Q(type='tech')
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
        condition |= Q(type='appro')
        
    demandes = Helpdesk.objects.filter(condition).order_by('-time_send')

    # Pré-traitement pour gérer le champ file_path
    for demande in demandes:
        if demande.file_path:
            demande.files = [file.strip() for file in demande.file_path.split(',')]
        else:
            demande.files = []

    context = {
        'demandes': demandes,
        'title': "Liste des demandes",
        'user': user,
        'has_dept_perm': has_dept_perm,
    }
    return render(request, 'helpdesk/dashboard.html', context)



@permission_required('accueil.view_menu_items_dashboard', raise_exception=True)
@login_required
def mark_terminee(request, demande_id):
    if request.method == "POST":
        demande = get_object_or_404(Helpdesk, id=demande_id)
        demande.time_terminee = timezone.now()
        demande.terminee_par = request.user.username
        demande.save()
        messages.success(request, "La demande a été conclue avec succès!")
    return redirect('dashboard')  # Assurez-vous que l'URL 'dashboard' soit bien nommée dans urls.py


from django.http import FileResponse, Http404
import os
from django.conf import settings

def download_file(request, filename):
    file_path = os.path.join(settings.MEDIA_ROOT, filename)

    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True)
    else:
        raise Http404("Fichier non trouvé")
