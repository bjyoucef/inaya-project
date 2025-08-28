class PrestationUpdateView(View):
    """Vue de modification simplifiée"""

    def get(self, request, prestation_id):
        from pharmacies.models import Produit

        prestation = get_object_or_404(PrestationKt, id=prestation_id)

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_actif=True)

        services = services_autorises(request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            conventions_acte = (
                Convention.objects.filter(tarifs_acte__acte=acte, active=True)
                .distinct()
                .values("id", "nom")
            )

            actes_data.append(
                {
                    "id": acte.id,
                    "code": acte.code,
                    "libelle": acte.libelle,
                    "conventions": list(conventions_acte),
                }
            )

        # Préparer les données des actes existants
        prestation_actes = []
        for pa in prestation.actes_details.all():
            consommations = [
                {
                    "produit_id": cp.produit.id,
                    "quantite_defaut": cp.quantite_defaut,
                    "quantite_reelle": cp.quantite_reelle,
                    "prix_unitaire": float(cp.prix_unitaire),
                }
                for cp in pa.consommations.all()
            ]
            prestation_actes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else None,
                    "convention_accordee": pa.convention_accordee,
                    "dossier_convention_complet": pa.dossier_convention_complet,  # NOUVEAU
                    "tarif": float(pa.tarif_conventionne),
                    "consommations": consommations,
                }
            )

        context = {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "prestation_actes_json": json.dumps(prestation_actes),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
        }

        return render(request, "prestations/update.html", context)

    def _get_context_data(self, prestation):
        """Méthode helper pour récupérer le contexte en cas d'erreur"""
        from pharmacies.models import Produit

        patients = Patient.objects.all()
        medecins = Medecin.objects.all()
        all_prods = Produit.objects.filter(est_actif=True)

        services = services_autorises(self.request.user)
        service_ids = list(services.values_list("id", flat=True))

        actes = ActeKt.objects.filter(service__id__in=service_ids)
        actes_data = []

        for acte in actes:
            conventions_acte = (
                Convention.objects.filter(tarifs_acte__acte=acte, active=True)
                .distinct()
                .values("id", "nom")
            )

            actes_data.append(
                {
                    "id": acte.id,
                    "code": acte.code,
                    "libelle": acte.libelle,
                    "conventions": list(conventions_acte),
                }
            )

        # Préparer les données des actes existants
        prestation_actes = []
        for pa in prestation.actes_details.all():
            consommations = [
                {
                    "produit_id": cp.produit.id,
                    "quantite_defaut": cp.quantite_defaut,
                    "quantite_reelle": cp.quantite_reelle,
                    "prix_unitaire": float(cp.prix_unitaire),
                }
                for cp in pa.consommations.all()
            ]
            prestation_actes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else None,
                    "convention_accordee": pa.convention_accordee,
                    "dossier_convention_complet": pa.dossier_convention_complet,  # NOUVEAU
                    "tarif": float(pa.tarif_conventionne),
                    "consommations": consommations,
                }
            )

        return {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": PrestationKt.STATUT_CHOICES,
            "actes_json": json.dumps(actes_data),
            "prestation_actes_json": json.dumps(prestation_actes),
            "all_produits": all_prods,
            "all_produits_json": json.dumps(
                [
                    {**prod, "prix_vente": float(prod["prix_vente"])}
                    for prod in all_prods.values(
                        "id", "code_produit", "nom", "prix_vente"
                    )
                ]
            ),
        }

    @transaction.atomic
    def post(self, request, prestation_id):
        prestation = get_object_or_404(PrestationKt, id=prestation_id)

        errors = []
        # Champs obligatoires
        patient_id = request.POST.get("patient")
        medecin_id = request.POST.get("medecin")
        date_str = request.POST.get("date_prestation")
        statut = request.POST.get("statut")
        observations = request.POST.get("observations", "").strip()

        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        conv_ok_vals = request.POST.getlist("convention_accordee[]")
        dossier_complet_vals = request.POST.getlist("dossier_convention_complet[]")

        if not (patient_id and medecin_id and date_str and statut):
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if not acte_ids:
            errors.append("Au moins un acte doit être sélectionné.")

        # Conversion de la date
        try:
            date_prest = timezone.datetime.strptime(date_str, "%Y-%m-%d")
            # Make it timezone-aware
            if timezone.is_naive(date_prest):
                date_prest = timezone.make_aware(date_prest)
        except (ValueError, TypeError):
            errors.append("Format de date invalide.")

        prestation_data = []
        conso_data = []
        total = Decimal("0.00")

        # Validation des actes
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = ActeKt.objects.get(pk=acte_pk)
                conv = None
                conv_ok = False
                dossier_complet = False

                if convention_ids and idx < len(convention_ids) and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    if idx < len(conv_ok_vals):
                        conv_ok = conv_ok_vals[idx] == "oui"
                    if idx < len(dossier_complet_vals):
                        dossier_complet = dossier_complet_vals[idx] == "oui"

                tarif = (
                    Decimal(tarifs[idx] or "0") if idx < len(tarifs) else Decimal("0")
                )
                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                        "dossier_convention_complet": dossier_complet,
                    }
                )

                # Récupération des consommations par acte (pour facturation uniquement)
                prod_field = f"actes[{idx}][produits][]"
                qty_field = f"actes[{idx}][quantites_reelles][]"
                for pid, qty in zip(
                    request.POST.getlist(prod_field), request.POST.getlist(qty_field)
                ):
                    if pid and qty:  # Vérifier que les valeurs ne sont pas vides
                        conso_data.append(
                            {
                                "idx": idx,
                                "produit_id": pid,
                                "quantite_reelle": qty,
                            }
                        )

            except ActeKt.DoesNotExist:
                errors.append(f"ActeKt invalide à la ligne {idx+1}.")
            except Convention.DoesNotExist:
                errors.append(f"Convention invalide à la ligne {idx+1}.")
            except InvalidOperation:
                errors.append(f"Tarif invalide à la ligne {idx+1}.")
            except Exception as e:
                errors.append(f"Erreur ligne {idx+1} : {e}")

        if errors:
            # Retourner le formulaire avec les erreurs en utilisant la méthode helper
            context = self._get_context_data(prestation)
            context["errors"] = errors
            return render(request, "prestations/update.html", context)

        # Récupérer les nouveaux objets
        nouveau_prix_supplementaire = Decimal(
            request.POST.get("prix_supplementaire", "0")
        )

        # Mise à jour de la prestation
        prestation.patient_id = patient_id
        prestation.medecin_id = medecin_id
        prestation.date_prestation = date_prest
        prestation.statut = statut
        prestation.observations = observations
        prestation.prix_total = total
        prestation.prix_supplementaire = nouveau_prix_supplementaire
        prestation.save()

        # Supprimer les anciens actes et consommations
        prestation.actes_details.all().delete()

        # Créer les nouveaux PrestationActe et consommations
        for idx, d in enumerate(prestation_data):
            pa = PrestationActe.objects.create(
                prestation=prestation,
                acte=d["acte"],
                convention=d["convention"],
                convention_accordee=d["convention_accordee"],
                dossier_convention_complet=d["dossier_convention_complet"],
                tarif_conventionne=d["tarif"],
            )

            # Traitement des consommations (pour facturation uniquement)
            for c in [c for c in conso_data if c["idx"] == idx]:
                if not c["produit_id"] or int(c["quantite_reelle"]) <= 0:
                    continue

                try:
                    prod = get_object_or_404(Produit, id=c["produit_id"])
                    quantite_reelle = int(c["quantite_reelle"])

                    try:
                        acte_produit = ActeProduit.objects.get(
                            acte=d["acte"], produit=prod
                        )
                        qte_defaut = acte_produit.quantite_defaut
                    except ActeProduit.DoesNotExist:
                        qte_defaut = 0

                    ConsommationProduit.objects.create(
                        prestation_acte=pa,
                        produit=prod,
                        quantite_defaut=qte_defaut,
                        quantite_reelle=quantite_reelle,
                        prix_unitaire=prod.prix_vente,
                    )
                except Exception as e:
                    # Log l'erreur mais continuez le traitement
                    print(f"Erreur lors de la création de la consommation: {e}")

        messages.success(request, "Prestation modifiée avec succès.")
        return redirect("medical:prestation_detail", prestation_id=prestation.id)
