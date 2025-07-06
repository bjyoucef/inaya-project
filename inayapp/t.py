# views.py
class PrestationUpdateView(View):
    def get(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        services = services_autorises(request.user)

        # Optimisation des requêtes
        patients = Patient.objects.all().only("id", "nom", "prenom")
        medecins = Medecin.objects.all().only("id", "nom", "prenom")
        all_prods = Produit.objects.filter(est_actif=True).values(
            "id", "code_produit", "nom", "prix_vente"
        )

        # Chargement des actes avec préfetch optimisé
        actes_qs = Acte.objects.filter(service__in=services).prefetch_related(
            Prefetch("conventions", queryset=Convention.objects.only("id", "nom")),
            Prefetch(
                "produits_defaut",
                queryset=ActeProduit.objects.select_related("produit"),
            ),
        )

        actes_data = [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": [
                    {"id": c.id, "nom": c.nom} for c in acte.conventions.all()
                ],
            }
            for acte in actes_qs
        ]

        # Préparation des lignes existantes
        lignes = []
        for pa in (
            prestation.actes_details.select_related("acte", "convention")
            .prefetch_related(
                Prefetch(
                    "consommations",
                    queryset=ConsommationProduit.objects.select_related("produit"),
                )
            )
            .all()
        ):
            consommations = [
                {
                    "produit_id": conso.produit.id,
                    "quantite_defaut": conso.quantite_defaut,
                    "quantite_reelle": conso.quantite_reelle,
                }
                for conso in pa.consommations.all()
            ]

            lignes.append(
                {
                    "acte_id": pa.acte.id,
                    "convention_id": pa.convention.id if pa.convention else None,
                    "tarif": float(pa.tarif_conventionne),
                    "consommations": consommations,
                }
            )

        context = {
            "prestation": prestation,
            "patients": patients,
            "medecins": medecins,
            "statut_choices": Prestation.STATUT_CHOICES,
            "actes_json": mark_safe(json.dumps(actes_data)),  # Correction sécurité
            "lignes": mark_safe(json.dumps(lignes)),  # Correction sécurité
            "all_produits": all_prods,
            "all_produits_json": mark_safe(json.dumps(list(all_prods))),
        }

        return render(request, "prestations/update.html", context)

    @transaction.atomic
    def post(self, request, prestation_id):
        prestation = get_object_or_404(Prestation, pk=prestation_id)
        services = services_autorises(request.user)
        errors = []
        prestation_data = []
        conso_data = []
        total = Decimal("0.00")

        # Validation des champs obligatoires
        required_fields = {
            "patient": "Patient requis",
            "medecin": "Médecin requis",
            "date_prestation": "Date de réalisation requise",
            "statut": "Statut requis",
        }

        for field, msg in required_fields.items():
            if not request.POST.get(field):
                errors.append(msg)

        # Traitement des actes
        acte_ids = request.POST.getlist("actes[]")
        convention_ids = request.POST.getlist("conventions[]")
        tarifs = request.POST.getlist("tarifs[]")
        conv_ok_vals = request.POST.getlist("convention_accordee[]")

        if not acte_ids:
            errors.append("Au moins un acte est requis")

        # Validation de chaque ligne d'acte
        for idx, acte_pk in enumerate(acte_ids):
            try:
                acte = Acte.objects.get(pk=acte_pk)
                if acte.service.id not in services.values_list("id", flat=True):
                    errors.append(f"Acte non autorisé à la ligne {idx+1}")
                    continue

                conv = None
                conv_ok = False
                if convention_ids and idx < len(convention_ids) and convention_ids[idx]:
                    conv = Convention.objects.get(pk=convention_ids[idx])
                    if conv not in acte.conventions.all():
                        errors.append(
                            f"Convention non liée à l'acte à la ligne {idx+1}"
                        )
                        continue
                    conv_ok = (
                        conv_ok_vals[idx] == "oui" if idx < len(conv_ok_vals) else False
                    )

                # Validation numérique sécurisée
                try:
                    tarif = Decimal(tarifs[idx]) if idx < len(tarifs) else Decimal("0")
                except (InvalidOperation, TypeError, ValueError):
                    errors.append(f"Tarif invalide à la ligne {idx+1}")
                    continue

                if tarif < Decimal("0"):
                    errors.append(f"Tarif négatif à la ligne {idx+1}")
                    continue

                total += tarif
                prestation_data.append(
                    {
                        "acte": acte,
                        "convention": conv,
                        "tarif": tarif,
                        "convention_accordee": conv_ok,
                    }
                )

                # Traitement des consommations
                produit_ids = request.POST.getlist(f"actes[{idx}][produits][]")
                quantites = request.POST.getlist(f"actes[{idx}][quantites_reelles][]")

                for prod_idx, (pid, qty) in enumerate(zip(produit_ids, quantites)):
                    if not pid or not qty:
                        continue

                    try:
                        produit = Produit.objects.get(id=pid, est_actif=True)
                        quantite_reelle = int(qty)

                        if quantite_reelle <= 0:
                            continue

                        conso_data.append(
                            {
                                "idx": idx,
                                "produit": produit,
                                "quantite_reelle": quantite_reelle,
                            }
                        )
                    except (Produit.DoesNotExist, ValueError):
                        errors.append(
                            f"Produit ou quantité invalide à la ligne {idx+1}, produit {prod_idx+1}"
                        )

            except (Acte.DoesNotExist, Convention.DoesNotExist):
                errors.append(f"Acte ou convention invalide à la ligne {idx+1}")

        # Gestion des erreurs
        if errors:
            return self.render_error_context(prestation, services, errors)

        # Mise à jour de la prestation
        try:
            prestation.patient_id = request.POST["patient"]
            prestation.medecin_id = request.POST["medecin"]
            prestation.date_prestation = request.POST[
                "date_prestation"
            ]  # Stockage comme string
            prestation.statut = request.POST["statut"]
            prestation.observations = request.POST.get("observations", "")
            prestation.prix_total = total
            prestation.prix_supplementaire = Decimal(
                request.POST.get("prix_supplementaire", "0")
            )
            prestation.save()
        except (ValueError, TypeError) as e:
            errors.append(f"Erreur dans les données: {str(e)}")
            return self.render_error_context(prestation, services, errors)

        # Recréation des actes et consommations
        with transaction.atomic():
            prestation.actes_details.all().delete()

            for idx, data in enumerate(prestation_data):
                pa = PrestationActe.objects.create(
                    prestation=prestation,
                    acte=data["acte"],
                    convention=data["convention"],
                    convention_accordee=data["convention_accordee"],
                    tarif_conventionne=data["tarif"],
                )

                # Création des consommations
                for conso in filter(lambda c: c["idx"] == idx, conso_data):
                    try:
                        acte_produit = ActeProduit.objects.get(
                            acte=data["acte"], produit=conso["produit"]
                        )
                        qte_defaut = acte_produit.quantite_defaut
                    except ActeProduit.DoesNotExist:
                        qte_defaut = 0

                    ConsommationProduit.objects.create(
                        prestation_acte=pa,
                        produit=conso["produit"],
                        quantite_defaut=qte_defaut,
                        quantite_reelle=conso["quantite_reelle"],
                        prix_unitaire=conso["produit"].prix_vente,
                    )

            prestation.update_stock()

        return redirect("medical:prestation_detail", prestation_id=prestation.id)

    def render_error_context(self, prestation, services, errors):
        # Optimisation du rechargement des données en cas d'erreur
        context = {
            "errors": errors,
            "prestation": prestation,
            "patients": Patient.objects.all().only("id", "nom", "prenom"),
            "medecins": Medecin.objects.all().only("id", "nom", "prenom"),
            "statut_choices": Prestation.STATUT_CHOICES,
            "actes_json": mark_safe(json.dumps(self.get_actes_data(services))),
            "all_produits": Produit.objects.filter(est_actif=True),
            "all_produits_json": mark_safe(
                json.dumps(
                    list(
                        Produit.objects.filter(est_actif=True).values(
                            "id", "code_produit", "nom", "prix_vente"
                        )
                    )
                )
            ),
        }
        return render(self.request, "prestations/update.html", context)

    def get_actes_data(self, services):
        actes_qs = Acte.objects.filter(service__in=services).prefetch_related(
            "conventions"
        )
        return [
            {
                "id": acte.id,
                "code": acte.code,
                "libelle": acte.libelle,
                "conventions": [
                    {"id": c.id, "nom": c.nom} for c in acte.conventions.all()
                ],
            }
            for acte in actes_qs
        ]
