# helpdesk/views.py
import base64
import datetime
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
import mimetypes

from .models import Helpdesk


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
    return render(request, 'demande_assistance.html', context)


# Fonction générique pour traiter la demande (améliorée)
def traiter_demande(request, demande_type):
    if request.method != 'POST':
        return redirect('demande_assistance')

    # Récupération des données
    ip_address = request.META.get('REMOTE_ADDR', '')
    name = request.POST.get('name')
    demande_details = request.POST.get('demande_details')
    audio_data = request.POST.get('audioData')
    files = request.FILES.getlist('file_upload')

    # Nouvelles données du modal d'aide global
    urgence = request.POST.get('urgence', 'normale')
    contact_preference = request.POST.get('contact_preference', 'email')

    # Validation des champs obligatoires
    if not name or not demande_details:
        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
        return redirect('demande_assistance')

    # Enrichissement de la description avec les informations supplémentaires
    details_enrichis = demande_details
    if urgence or contact_preference:
        details_enrichis += f"\n\n--- Informations de la demande ---"
        if urgence:
            urgence_labels = {
                'faible': 'Faible',
                'normale': 'Normale',
                'elevee': 'Élevée'
            }
            details_enrichis += f"\nNiveau d'urgence: {urgence_labels.get(urgence, urgence)}"

        if contact_preference:
            contact_labels = {
                'email': 'Email',
                'telephone': 'Téléphone',
                'sur_place': 'Intervention sur place',
                'remote': 'Assistance à distance'
            }
            details_enrichis += f"\nPréférence de contact: {contact_labels.get(contact_preference, contact_preference)}"

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
        helpdesk_instance = Helpdesk.objects.create(
            ip_address=ip_address,
            name=name,
            type=demande_type,
            details=details_enrichis,  # Utilisation des détails enrichis
            file_path=file_paths_str,
            audio_path=audio_path,
            time_send=datetime.datetime.now()
        )

        # Message de succès personnalisé selon l'urgence
        if urgence == 'elevee':
            messages.success(request,
                             "🚨 Demande urgente envoyée avec succès! Notre équipe sera notifiée immédiatement.")
        else:
            messages.success(request,
                             "✅ Demande envoyée avec succès! Vous recevrez une réponse dans les plus brefs délais.")

        # Log pour le suivi (optionnel)
        print(
            f"Nouvelle demande {demande_type} - ID: {helpdesk_instance.id} - Urgence: {urgence} - Contact: {contact_preference}")

    except Exception as e:
        messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")

    previous_url = request.META.get("HTTP_REFERER", "/")
    return redirect(previous_url)


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

    # Construction de la condition de filtrage
    condition = Q(name=str(id_personnel))  # Convertir en string pour comparaison
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_IT'):
        condition |= Q(type='it')
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE'):
        condition |= Q(type='tech')
    if request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
        condition |= Q(type='appro')

    demandes = Helpdesk.objects.filter(condition).order_by('-time_send')

    # Pré-traitement pour gérer le champ file_path et enrichir les données
    for demande in demandes:
        if demande.file_path:
            demande.files = [file.strip() for file in demande.file_path.split(',')]
        else:
            demande.files = []

        # Extraction des informations d'urgence et de contact des détails
        demande.urgence_level = 'normale'  # Valeur par défaut
        demande.contact_pref = 'email'  # Valeur par défaut

        if "Niveau d'urgence:" in demande.details:
            try:
                urgence_line = [line for line in demande.details.split('\n')
                                if "Niveau d'urgence:" in line][0]
                if 'Élevée' in urgence_line:
                    demande.urgence_level = 'elevee'
                elif 'Faible' in urgence_line:
                    demande.urgence_level = 'faible'
                else:
                    demande.urgence_level = 'normale'
            except:
                pass

        if "Préférence de contact:" in demande.details:
            try:
                contact_line = [line for line in demande.details.split('\n')
                                if "Préférence de contact:" in line][0]
                if 'Téléphone' in contact_line:
                    demande.contact_pref = 'telephone'
                elif 'sur place' in contact_line.lower():
                    demande.contact_pref = 'sur_place'
                elif 'distance' in contact_line.lower():
                    demande.contact_pref = 'remote'
            except:
                pass

    # Statistiques pour le dashboard
    stats = {
        'total_demandes': demandes.count(),
        'demandes_urgentes': demandes.filter(details__icontains="Niveau d'urgence: Élevée").count(),
        'demandes_ouvertes': demandes.filter(time_terminee__isnull=True).count(),
        'demandes_terminees': demandes.filter(time_terminee__isnull=False).count(),
    }

    context = {
        'demandes': demandes,
        'title': "Dashboard - Helpdesk",
        'user': user,
        'has_dept_perm': has_dept_perm,
        'stats': stats,
    }
    return render(request, 'dashboard_hd.html', context)


@permission_required('accueil.view_menu_items_dashboard', raise_exception=True)
@login_required
def mark_terminee(request, demande_id):
    if request.method == "POST":
        demande = get_object_or_404(Helpdesk, id=demande_id)
        demande.time_terminee = timezone.now()
        demande.terminee_par = request.user.username
        demande.save()

        # Message de succès avec le nom de la demande
        messages.success(request,
                         f"✅ La demande #{demande.id} de {demande.name} a été marquée comme terminée!")

    return redirect('dashboard')


@login_required
def download_file(request, filename):
    """Téléchargement sécurisé des fichiers"""
    file_path = os.path.join(settings.MEDIA_ROOT, filename)

    if os.path.exists(file_path):
        # Déterminer le type MIME
        content_type, _ = mimetypes.guess_type(file_path)

        # Pour les fichiers audio, ne pas forcer le téléchargement
        if content_type and content_type.startswith('audio/'):
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type,
                as_attachment=False  # Permet la lecture directe
            )
            # Ajouter les headers CORS si nécessaire
            response['Access-Control-Allow-Origin'] = '*'
            response['Accept-Ranges'] = 'bytes'
            return response
        else:
            # Pour les autres fichiers, forcer le téléchargement
            return FileResponse(open(file_path, 'rb'), as_attachment=True)
    else:
        raise Http404("Fichier non trouvé")


@login_required
def serve_audio(request, audio_path):
    """Vue spécifique pour servir les fichiers audio avec streaming"""
    file_path = os.path.join(settings.MEDIA_ROOT, audio_path)

    if not os.path.exists(file_path):
        raise Http404("Fichier audio non trouvé")

    # Vérifier que c'est bien un fichier audio
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = 'audio/wav'  # Fallback pour les fichiers .wav

    file_size = os.path.getsize(file_path)

    # Gestion des requêtes Range pour le streaming
    range_header = request.META.get('HTTP_RANGE', '').strip()

    if range_header:
        import re
        range_match = re.search(r'bytes\s*=\s*(\d+)\s*-\s*(\d*)', range_header)

        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

            if start >= file_size:
                return HttpResponse(status=416)  # Range Not Satisfiable

            with open(file_path, 'rb') as audio_file:
                audio_file.seek(start)
                chunk_size = end - start + 1
                data = audio_file.read(chunk_size)

            response = HttpResponse(
                data,
                status=206,  # Partial Content
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Content-Length'] = str(chunk_size)
            response['Accept-Ranges'] = 'bytes'
            response['Access-Control-Allow-Origin'] = '*'

            return response

    # Requête normale (sans Range)
    try:
        with open(file_path, 'rb') as audio_file:
            data = audio_file.read()

        response = HttpResponse(data, content_type=content_type)
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=3600'
        response['Access-Control-Allow-Origin'] = '*'

        return response

    except IOError:
        raise Http404("Erreur lors de la lecture du fichier audio")


@require_http_methods(["GET"])
@login_required
def get_demande_details(request, demande_id):
    """API pour récupérer les détails d'une demande (pour modal/popup)"""
    try:
        demande = get_object_or_404(Helpdesk, id=demande_id)

        # Vérifier les permissions
        user_id = str(request.user.id)
        can_view = (
                demande.name == user_id or
                (demande.type == 'it' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_IT')) or
                (demande.type == 'tech' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE')) or
                (demande.type == 'appro' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'))
        )

        if not can_view:
            return JsonResponse({'error': 'Permission refusée'}, status=403)

        data = {
            'id': demande.id,
            'name': demande.name,
            'type': demande.type,
            'details': demande.details,
            'time_send': demande.time_send.strftime('%d/%m/%Y %H:%M') if demande.time_send else '',
            'time_terminee': demande.time_terminee.strftime('%d/%m/%Y') if demande.time_terminee else None,
            'terminee_par': demande.terminee_par,
            'files': demande.file_path.split(',') if demande.file_path else [],
            'has_audio': bool(demande.audio_path),
            'audio_path': demande.audio_path,
            'ip_address': demande.ip_address,
        }

        return JsonResponse(data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def update_demande_status(request, demande_id):
    """API pour mettre à jour le statut d'une demande"""
    try:
        demande = get_object_or_404(Helpdesk, id=demande_id)

        # Vérifier les permissions (seuls les départements peuvent modifier)
        can_modify = (
                (demande.type == 'it' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_IT')) or
                (demande.type == 'tech' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_TECHNIQUE')) or
                (demande.type == 'appro' and request.user.has_perm('helpdesk.ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'))
        )

        if not can_modify:
            return JsonResponse({'error': 'Permission refusée'}, status=403)

        action = request.POST.get('action')

        if action == 'mark_terminee':
            demande.time_terminee = timezone.now()
            demande.terminee_par = request.user.username
            demande.save()

            return JsonResponse({
                'success': True,
                'message': f'Demande #{demande.id} marquée comme terminée',
                'time_terminee': demande.time_terminee.strftime('%d/%m/%Y %H:%M')
            })
        elif action == 'reopen':
            demande.time_terminee = None
            demande.terminee_par = None
            demande.save()

            return JsonResponse({
                'success': True,
                'message': f'Demande #{demande.id} réouverte'
            })
        else:
            return JsonResponse({'error': 'Action non reconnue'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)