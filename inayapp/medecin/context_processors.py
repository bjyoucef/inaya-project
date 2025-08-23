# medecin/context_processors.py
def medecin_stats(request):
    """
    Context processor pour les statistiques globales des médecins
    """
    if request.path.startswith("/medecin/"):
        return {"medecin_stats": get_medecin_stats()}
    return {}
