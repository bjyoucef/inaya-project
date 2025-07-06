@audit_view
def create_decharge_medecin(request, medecin_id):
    medecin = get_object_or_404(Medecin, pk=medecin_id)
    prestations_non_dechargees = (
        PrestationActe.objects.filter(prestation__medecin=medecin)
        .exclude(decharges__isnull=False)
        .select_related("prestation", "acte", "convention", "prestation__patient")
    )

    if request.method == "POST":
        # Création de la décharge
        decharge = Decharges.objects.create(
            name=request.POST.get("nom_decharge"),
            amount=0,
            date=request.POST.get("date_decharge"),
            medecin=medecin,
            id_created_par=request.user,
        )

        # Ajout des prestations et construction de la note
        prestation_ids = request.POST.getlist("prestation_acte_ids")
        prestations = PrestationActe.objects.filter(
            id__in=prestation_ids
        ).select_related("prestation")
        decharge.prestation_actes.set(prestations)

        # Génération automatique de la note
        note_content = [
            f"Décharge médicale - Dr. {medecin.nom_complet}\n",
            f"Date de création: {decharge.date}\n\n",
            "Prestations incluses:\n",
        ]

        total_honoraires = 0
        total_supplementaire = 0

        for prestation in prestations:
            details = [
                f"Date: {prestation.prestation.date_prestation.date()}",
                f"Acte: {prestation.acte.libelle} ({prestation.acte.code})",
                f"Patient: {prestation.prestation.patient.nom_complet}",
                f"Convention: {prestation.convention.nom if prestation.convention else 'Non conventionné'}",
                f"Honoraire: {prestation.honoraire_medecin} DA",
            ]

            # Ajouter le prix supplémentaire médecin s'il existe
            if prestation.prestation.prix_supplementaire_medecin > 0:
                details.append(
                    f"Supplément médecin: {prestation.prestation.prix_supplementaire_medecin} DA"
                )
                total_supplementaire += (
                    prestation.prestation.prix_supplementaire_medecin
                )

            note_content.append(" | ".join(details))
            total_honoraires += prestation.honoraire_medecin

        # Calcul et ajout du total
        total_general = total_honoraires + total_supplementaire

        note_content.append(f"\nRécapitulatif:")
        note_content.append(f"Total honoraires: {total_honoraires} DA")
        if total_supplementaire > 0:
            note_content.append(f"Total suppléments médecin: {total_supplementaire} DA")
        note_content.append(f"Total général: {total_general} DA")

        decharge.note = "\n".join(note_content)
        decharge.amount = total_general
        decharge.save()

        return redirect("decharge_list")

    context = {
        "medecin": medecin,
        "prestations": prestations_non_dechargees,
    }
    return render(request, "decharges/create_decharge_medecin.html", context)
