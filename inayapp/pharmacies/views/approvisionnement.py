# pharmacies/views/approvisionnement.py
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (CreateView, DetailView, ListView, UpdateView,
                                  View)
from medical.models.services import Service

from ..models.approvisionnement import (BonReception, CommandeFournisseur,
                                        DemandeInterne, ExpressionBesoin,
                                        LigneBesoin, LigneCommande,
                                        LigneDemandeInterne, LigneLivraison,
                                        Livraison)
from ..models.fournisseur import Fournisseur
from ..models.produit import Produit
from ..models.stock import Stock


class ExpressionBesoinListView(LoginRequiredMixin, ListView):
    model = ExpressionBesoin
    template_name = "approvisionnement/expression_besoin_list.html"
    context_object_name = "besoins"
    paginate_by = 20

    def get_queryset(self):
        queryset = ExpressionBesoin.objects.select_related(
            "service_demandeur", "service_approvisionneur", "valide_par"
        ).prefetch_related("lignes__produit")

        # Filtrage par statut
        statut = self.request.GET.get("statut")
        if statut:
            queryset = queryset.filter(statut=statut)

        # Filtrage par service
        service_id = self.request.GET.get("service")
        if service_id:
            queryset = queryset.filter(service_demandeur_id=service_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["services"] = Service.objects.filter(est_actif=True)
        context["statuts"] = ExpressionBesoin.STATUT_CHOICES
        return context


class ExpressionBesoinDetailView(LoginRequiredMixin, DetailView):
    model = ExpressionBesoin
    template_name = "approvisionnement/expression_besoin_detail.html"
    context_object_name = "besoin"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.select_related("produit")
        return context


class ExpressionBesoinCreateView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            "services": Service.objects.filter(est_actif=True, est_stockeur=True),
            "services_pharmacie": Service.objects.filter(est_pharmacies=True),
            "produits": Produit.objects.filter(est_actif=True).order_by("nom"),
        }

        return render(request, "approvisionnement/expression_besoin_form.html", context)

    @method_decorator(csrf_exempt)
    def post(self, request):
        try:
            data = json.loads(request.body)

            with transaction.atomic():
                # Créer l'expression de besoin
                besoin = ExpressionBesoin.objects.create(
                    type_approvisionnement=data.get(
                        "type_approvisionnement", "EXTERNE"
                    ),
                    service_demandeur_id=data["service_demandeur"],
                    service_approvisionneur_id=data["service_approvisionneur"],
                    priorite=data.get("priorite", "NORMALE"),
                    created_by=request.user,
                )

                # Créer les lignes
                for ligne_data in data["lignes"]:
                    LigneBesoin.objects.create(
                        besoin=besoin,
                        produit_id=ligne_data["produit_id"],
                        quantite_demandee=ligne_data["quantite_demandee"],
                    )

                # Si c'est un approvisionnement interne, créer la demande interne
                if besoin.est_approvisionnement_interne:
                    demande_interne = DemandeInterne.objects.create(
                        besoin=besoin, service_destinataire=besoin.service_demandeur
                    )

                    # Créer les lignes de demande interne
                    for ligne_besoin in besoin.lignes.all():
                        LigneDemandeInterne.objects.create(
                            demande=demande_interne,
                            produit=ligne_besoin.produit,
                            quantite_demandee=ligne_besoin.quantite_demandee,
                        )

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Expression de besoin créée avec succès",
                        "redirect_url": reverse_lazy(
                            "pharmacies:expression_besoin_detail",
                            kwargs={"pk": besoin.pk},
                        ),
                    }
                )

        except Exception as e:
            return JsonResponse(
                {"success": False, "message": f"Erreur lors de la création: {str(e)}"},
                status=400,
            )


class ExpressionBesoinValidationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        besoin = get_object_or_404(ExpressionBesoin, pk=pk)

        try:
            data = json.loads(request.body)
            action = data.get("action")

            if action == "valider":
                besoin.valider(request.user)

                # Mise à jour des quantités validées
                for ligne_data in data.get("lignes", []):
                    ligne = besoin.lignes.get(id=ligne_data["id"])
                    ligne.quantite_validee = ligne_data["quantite_validee"]
                    ligne.save()

                messages.success(request, "Expression de besoin validée avec succès")

            elif action == "rejeter":
                besoin.statut = "REJETE"
                besoin.save()
                messages.success(request, "Expression de besoin rejetée")

            return JsonResponse({"success": True})

        except ValidationError as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class DemandeInterneListView(LoginRequiredMixin, ListView):
    model = DemandeInterne
    template_name = "approvisionnement/demande_interne_list.html"
    context_object_name = "demandes"
    paginate_by = 20

    def get_queryset(self):
        queryset = DemandeInterne.objects.select_related(
            "besoin__service_demandeur",
            "service_destinataire",
            "validee_par",
            "preparee_par",
            "livree_par",
        ).prefetch_related("lignes__produit")

        # Filtrage par statut
        statut = self.request.GET.get("statut")
        if statut:
            queryset = queryset.filter(statut=statut)

        # Filtrage par service
        service_id = self.request.GET.get("service")
        if service_id:
            queryset = queryset.filter(service_destinataire_id=service_id)

        # Filtrage par priorité
        priorite = self.request.GET.get("priorite")
        if priorite:
            queryset = queryset.filter(besoin__priorite=priorite)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["services"] = Service.objects.filter(est_actif=True)
        context["statuts"] = DemandeInterne.STATUT_CHOICES
        context["priorites"] = ExpressionBesoin.PRIORITE_CHOICES

        # Statistiques
        stats = DemandeInterne.objects.aggregate(
            en_attente=Count("id", filter=Q(statut="EN_ATTENTE")),
            validees=Count("id", filter=Q(statut="VALIDEE")),
            preparees=Count("id", filter=Q(statut="PREPAREE")),
            livrees=Count("id", filter=Q(statut="LIVREE")),
        )
        context["stats"] = stats
        return context


class DemandeInterneDetailView(LoginRequiredMixin, DetailView):
    model = DemandeInterne
    template_name = "approvisionnement/demande_interne_detail.html"
    context_object_name = "demande"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.select_related("produit")

        # Vérifier la disponibilité des stocks pour chaque produit
        service_pharmacie = self.object.besoin.service_approvisionneur
        stocks_info = []

        for ligne in context["lignes"]:
            # Calculer le stock disponible en utilisant la méthode get_available
            # et en faisant la somme des quantités
            stocks_disponibles = Stock.objects.get_available(
                produit=ligne.produit, service=service_pharmacie
            )

            # Calculer la quantité totale disponible
            from django.db.models import Sum

            stock_disponible = (
                stocks_disponibles.aggregate(total=Sum("quantite"))["total"] or 0
            )

            stocks_info.append(
                {
                    "ligne": ligne,
                    "stock_disponible": stock_disponible,
                    "stock_suffisant": stock_disponible
                    >= (ligne.quantite_accordee or ligne.quantite_demandee),
                }
            )

        context["stocks_info"] = stocks_info
        return context


class DemandeInterneValidationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        try:
            data = json.loads(request.body)
            action = data.get("action")

            if action == "valider":
                demande.valider(request.user)

                # Mise à jour des quantités accordées
                for ligne_data in data.get("lignes", []):
                    ligne = demande.lignes.get(id=ligne_data["id"])
                    ligne.quantite_accordee = ligne_data["quantite_accordee"]
                    ligne.observations = ligne_data.get("observations", "")
                    ligne.save()

                messages.success(request, "Demande interne validée avec succès")

            elif action == "rejeter":
                demande.statut = "REJETEE"
                demande.observations = data.get("observations", "")
                demande.save()
                messages.success(request, "Demande interne rejetée")

            elif action == "preparer":
                demande.preparer(request.user)
                messages.success(request, "Demande interne préparée avec succès")

            elif action == "livrer":
                demande.livrer(request.user)
                messages.success(request, "Demande interne livrée avec succès")

            return JsonResponse({"success": True})

        except ValidationError as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class DemandeInterneValiderView(LoginRequiredMixin, View):
    """Vue pour valider une demande interne"""

    def post(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        if demande.statut != "EN_ATTENTE":
            messages.error(request, "Cette demande ne peut plus être validée.")
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        try:
            with transaction.atomic():
                # Récupérer les quantités accordées depuis le formulaire
                for ligne in demande.lignes.all():
                    quantite_accordee = request.POST.get(f"quantite_{ligne.pk}")
                    observation = request.POST.get(f"observation_{ligne.pk}", "")

                    if quantite_accordee:
                        ligne.quantite_accordee = int(quantite_accordee)
                        if observation:
                            ligne.observations = observation
                        ligne.save()

                # Observations générales
                observations_validation = request.POST.get(
                    "observations_validation", ""
                )
                if observations_validation:
                    demande.observations = f"{demande.observations}\n\nValidation: {observations_validation}".strip()

                # Valider la demande
                demande.valider(request.user)

                messages.success(request, "La demande a été validée avec succès.")

        except Exception as e:
            messages.error(request, f"Erreur lors de la validation : {str(e)}")

        return redirect("pharmacies:demande_interne_detail", pk=pk)


class DemandeInterneRejeterView(LoginRequiredMixin, View):
    """Vue pour rejeter une demande interne"""

    def post(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        if demande.statut != "EN_ATTENTE":
            messages.error(request, "Cette demande ne peut plus être rejetée.")
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        motif_rejet = request.POST.get("motif_rejet", "")

        if not motif_rejet:
            messages.error(request, "Le motif de rejet est obligatoire.")
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        try:
            demande.statut = "REJETEE"
            demande.date_rejet = timezone.now()
            demande.observations = (
                f"{demande.observations}\n\nMotif de rejet: {motif_rejet}".strip()
            )
            demande.save()

            messages.success(request, "La demande a été rejetée.")

        except Exception as e:
            messages.error(request, f"Erreur lors du rejet : {str(e)}")

        return redirect("pharmacies:demande_interne_detail", pk=pk)


class DemandeInternePreparerView(LoginRequiredMixin, View):
    """Vue pour marquer une demande comme préparée"""

    def post(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        if demande.statut != "VALIDEE":
            messages.error(
                request, "Seules les demandes validées peuvent être préparées."
            )
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        observations_preparation = request.POST.get("observations_preparation", "")

        try:
            if observations_preparation:
                demande.observations = f"{demande.observations}\n\nPréparation: {observations_preparation}".strip()

            demande.preparer(request.user)
            messages.success(request, "La demande a été marquée comme préparée.")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de la préparation : {str(e)}")

        return redirect("pharmacies:demande_interne_detail", pk=pk)


class DemandeInterneLivrerView(LoginRequiredMixin, View):
    """Vue pour livrer une demande interne"""

    def post(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        if demande.statut != "PREPAREE":
            messages.error(
                request, "Seules les demandes préparées peuvent être livrées."
            )
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        nom_receptionnaire = request.POST.get("nom_receptionnaire", "")
        observations_livraison = request.POST.get("observations_livraison", "")

        if not nom_receptionnaire:
            messages.error(request, "Le nom du réceptionnaire est obligatoire.")
            return redirect("pharmacies:demande_interne_detail", pk=pk)

        try:
            if observations_livraison or nom_receptionnaire:
                demande.observations = f"{demande.observations}\n\nLivraison: Réceptionné par {nom_receptionnaire}. {observations_livraison}".strip()

            demande.livrer(request.user)
            messages.success(request, "La demande a été livrée avec succès.")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur lors de la livraison : {str(e)}")

        return redirect("pharmacies:demande_interne_detail", pk=pk)


class DemandeInternePDFView(LoginRequiredMixin, View):
    """Vue pour générer le PDF d'une demande interne"""

    def get(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        # TODO: Implémenter la génération du PDF
        # Pour l'instant, retourner un placeholder
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="demande_interne_{demande.reference}.pdf"'
        )

        # Ici, utiliser une librairie comme ReportLab ou WeasyPrint pour générer le PDF
        response.write(b"PDF content would be here")

        return response


class DemandeInterneExcelView(LoginRequiredMixin, View):
    """Vue pour exporter une demande interne en Excel"""

    def get(self, request, pk):
        demande = get_object_or_404(DemandeInterne, pk=pk)

        # TODO: Implémenter l'export Excel
        # Pour l'instant, retourner un placeholder
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="demande_interne_{demande.reference}.xlsx"'
        )

        # Ici, utiliser une librairie comme openpyxl pour générer l'Excel
        response.write(b"Excel content would be here")

        return response


class CommandeFournisseurListView(LoginRequiredMixin, ListView):
    model = CommandeFournisseur
    template_name = "approvisionnement/commande_fournisseur_list.html"
    context_object_name = "commandes"
    paginate_by = 20

    def get_queryset(self):
        queryset = CommandeFournisseur.objects.select_related(
            "fournisseur", "besoin", "valide_par"
        ).prefetch_related("lignes__produit")

        # Filtrage par statut
        statut = self.request.GET.get("statut")
        if statut:
            queryset = queryset.filter(statut=statut)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuts"] = CommandeFournisseur.STATUT_CHOICES

        # Ajouter les statistiques
        stats = CommandeFournisseur.objects.aggregate(
            brouillon=Count("id", filter=Q(statut="BROUILLON")),
            en_attente=Count("id", filter=Q(statut="EN_ATTENTE")),
            confirme=Count("id", filter=Q(statut="CONFIRME")),
            livree=Count("id", filter=Q(statut="LIVREE")),
        )
        context["stats"] = stats
        return context


class CommandeFournisseurDetailView(LoginRequiredMixin, DetailView):
    model = CommandeFournisseur
    template_name = "approvisionnement/commande_fournisseur_detail.html"
    context_object_name = "commande"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.select_related("produit")
        return context


class CommandeFournisseurCreateView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            "fournisseurs": Fournisseur.objects.filter(statut="ACTIF"),
            "besoins": ExpressionBesoin.objects.filter(statut="VALIDE"),
            "produits": Produit.objects.filter(est_actif=True).order_by("nom"),
        }
        return render(
            request,
            "approvisionnement/commande_fournisseur_form.html",
            context,
        )

    @method_decorator(csrf_exempt)
    def post(self, request):
        try:
            data = json.loads(request.body)

            with transaction.atomic():
                # Créer la commande
                commande = CommandeFournisseur.objects.create(
                    fournisseur_id=data["fournisseur_id"],
                    besoin_id=data.get("besoin_id"),
                )

                # Créer les lignes
                for ligne_data in data["lignes"]:
                    LigneCommande.objects.create(
                        commande=commande,
                        produit_id=ligne_data["produit_id"],
                        quantite_commandee=ligne_data["quantite_commandee"],
                        prix_unitaire=Decimal(ligne_data["prix_unitaire"]),
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Commande créée avec succès",
                        "redirect_url": reverse_lazy(
                            "pharmacies:commande_fournisseur_detail",
                            kwargs={"pk": commande.pk},
                        ),
                    }
                )

        except Exception as e:
            return JsonResponse(
                {"success": False, "message": f"Erreur lors de la création: {str(e)}"},
                status=400,
            )


class CommandeFournisseurConfirmView(LoginRequiredMixin, View):
    def post(self, request, pk):
        commande = get_object_or_404(CommandeFournisseur, pk=pk)

        try:
            commande.confirmer(request.user)
            messages.success(request, "Commande confirmée avec succès")
            return JsonResponse({"success": True})

        except ValidationError as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class LivraisonListView(LoginRequiredMixin, ListView):
    model = Livraison
    template_name = "approvisionnement/livraison_list.html"
    context_object_name = "livraisons"
    paginate_by = 20

    def get_queryset(self):
        queryset = Livraison.objects.select_related(
            "commande__fournisseur", "recepteur"
        ).prefetch_related("lignes__produit")

        # Filtrage par statut
        statut = self.request.GET.get("statut")
        if statut:
            queryset = queryset.filter(statut=statut)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuts"] = Livraison.STATUT_CHOICES
        context["today"] = timezone.now().date()

        # Ajouter les statistiques
        today = timezone.now().date()
        stats = {
            "en_transit": Livraison.objects.filter(statut="EN_TRANSIT").count(),
            "partiel": Livraison.objects.filter(statut="PARTIEL").count(),
            "recu": Livraison.objects.filter(statut="RECU").count(),
            "retard": Livraison.objects.filter(
                statut="EN_TRANSIT", date_livraison_prevue__lt=today
            ).count(),
        }
        context["stats"] = stats
        return context


class LivraisonDetailView(LoginRequiredMixin, DetailView):
    model = Livraison
    template_name = "approvisionnement/livraison_detail.html"
    context_object_name = "livraison"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.select_related("produit")
        context["today"] = timezone.now().date()
        context["warning_date"] = timezone.now().date() + timedelta(days=30)

        # Calculer les totaux
        lignes = context["lignes"]
        context["total_quantite"] = sum(ligne.quantite_livree for ligne in lignes)
        context["lots_uniques"] = len(set(ligne.numero_lot for ligne in lignes))

        # Préparer les données de livraison pour la comparaison
        # Créer un dictionnaire {produit_id: quantite_livree}
        livraison_data = {}
        for ligne in lignes:
            produit_id = ligne.produit.id
            if produit_id in livraison_data:
                livraison_data[produit_id] += ligne.quantite_livree
            else:
                livraison_data[produit_id] = ligne.quantite_livree

        context["livraison_data"] = livraison_data

        # Alertes
        alertes = []
        if (
            self.object.date_livraison_prevue < timezone.now().date()
            and self.object.statut == "EN_TRANSIT"
        ):
            jours_retard = (
                timezone.now().date() - self.object.date_livraison_prevue
            ).days
            alertes.append(f"Livraison en retard de {jours_retard} jour(s)")

        # Vérifier les dates de péremption
        for ligne in lignes:
            if ligne.date_peremption < timezone.now().date():
                alertes.append(
                    f"Produit périmé détecté: {ligne.produit.nom} (lot {ligne.numero_lot})"
                )
            elif ligne.date_peremption < timezone.now().date() + timedelta(days=30):
                alertes.append(
                    f"Produit bientôt périmé: {ligne.produit.nom} (lot {ligne.numero_lot})"
                )

        context["alertes"] = alertes
        return context


class LivraisonCreateView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            "commandes": CommandeFournisseur.objects.filter(statut="EN_ATTENTE"),
        }
        return render(
            request, "approvisionnement/livraison_form.html", context
        )

    @method_decorator(csrf_exempt)
    def post(self, request):
        try:
            data = json.loads(request.body)

            with transaction.atomic():
                # Créer la livraison
                livraison = Livraison.objects.create(
                    commande_id=data["commande_id"],
                    date_livraison_prevue=data["date_livraison_prevue"],
                )

                # Créer les lignes
                for ligne_data in data["lignes"]:
                    LigneLivraison.objects.create(
                        livraison=livraison,
                        produit_id=ligne_data["produit_id"],
                        quantite_livree=ligne_data["quantite_livree"],
                        numero_lot=ligne_data["numero_lot"],
                        date_peremption=ligne_data["date_peremption"],
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Livraison créée avec succès",
                        "redirect_url": reverse_lazy(
                            "pharmacies:livraison_detail", kwargs={"pk": livraison.pk}
                        ),
                    }
                )

        except Exception as e:
            return JsonResponse(
                {"success": False, "message": f"Erreur lors de la création: {str(e)}"},
                status=400,
            )


class LivraisonReceptionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        livraison = get_object_or_404(Livraison, pk=pk)

        try:
            livraison.recevoir(request.user)
            messages.success(request, "Livraison reçue avec succès")
            return JsonResponse({"success": True})

        except ValidationError as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class BonReceptionListView(LoginRequiredMixin, ListView):
    model = BonReception
    template_name = "approvisionnement/bon_reception_list.html"
    context_object_name = "bons_reception"
    paginate_by = 20

    def get_queryset(self):
        queryset = BonReception.objects.select_related(
            "livraison__commande__fournisseur", "controleur"
        ).prefetch_related("livraison__lignes__produit")

        # Filtres
        fournisseur = self.request.GET.get("fournisseur")
        if fournisseur:
            queryset = queryset.filter(
                livraison__commande__fournisseur__nom__icontains=fournisseur
            )

        date_debut = self.request.GET.get("date_debut")
        if date_debut:
            queryset = queryset.filter(date_creation__date__gte=date_debut)

        date_fin = self.request.GET.get("date_fin")
        if date_fin:
            queryset = queryset.filter(date_creation__date__lte=date_fin)

        reference = self.request.GET.get("reference")
        if reference:
            queryset = queryset.filter(reference__icontains=reference)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Statistiques
        today = timezone.now().date()
        debut_semaine = today - timedelta(days=today.weekday())
        debut_mois = today.replace(day=1)

        stats = {
            "total": BonReception.objects.count(),
            "aujourdhui": BonReception.objects.filter(
                date_creation__date=today
            ).count(),
            "cette_semaine": BonReception.objects.filter(
                date_creation__date__gte=debut_semaine
            ).count(),
            "ce_mois": BonReception.objects.filter(
                date_creation__date__gte=debut_mois
            ).count(),
        }
        context["stats"] = stats
        return context


class BonReceptionDetailView(LoginRequiredMixin, DetailView):
    model = BonReception
    template_name = "approvisionnement/bon_reception_detail.html"
    context_object_name = "bon_reception"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = timezone.now().date()
        context["warning_date"] = timezone.now().date() + timedelta(days=30)

        # Alertes
        alertes = []
        for ligne in self.object.details_livraison:
            if ligne.date_peremption < timezone.now().date():
                alertes.append(
                    f"Produit périmé: {ligne.produit.nom} (lot {ligne.numero_lot})"
                )
            elif ligne.date_peremption < timezone.now().date() + timedelta(days=30):
                alertes.append(
                    f"Produit bientôt périmé: {ligne.produit.nom} (lot {ligne.numero_lot})"
                )

        context["alertes"] = alertes
        return context


class BonReceptionPrintView(LoginRequiredMixin, DetailView):
    model = BonReception
    template_name = "approvisionnement/bon_reception_print.html"
    context_object_name = "bon_reception"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Content-Type"] = "application/pdf"
        return response


# API Views pour les données dynamiques
class GetBesoinLignesAPIView(LoginRequiredMixin, View):
    def get(self, request, pk):
        besoin = get_object_or_404(ExpressionBesoin, pk=pk)
        lignes = []

        for ligne in besoin.lignes.select_related("produit"):
            lignes.append(
                {
                    "id": ligne.id,
                    "produit_id": ligne.produit.id,
                    "produit_nom": ligne.produit.nom,
                    "quantite_demandee": ligne.quantite_demandee,
                    "quantite_validee": ligne.quantite_validee,
                }
            )

        return JsonResponse({"lignes": lignes})


class GetCommandeLignesAPIView(LoginRequiredMixin, View):
    def get(self, request, pk):
        commande = get_object_or_404(CommandeFournisseur, pk=pk)
        lignes = []

        for ligne in commande.lignes.select_related("produit"):
            lignes.append(
                {
                    "id": ligne.id,
                    "produit_id": ligne.produit.id,
                    "produit_nom": ligne.produit.nom,
                    "quantite_commandee": ligne.quantite_commandee,
                    "prix_unitaire": str(ligne.prix_unitaire),
                }
            )

        return JsonResponse({"lignes": lignes})


class GetProduitsAPIView(LoginRequiredMixin, View):
    def get(self, request):
        produits = []

        for produit in Produit.objects.filter(est_actif=True).order_by("nom"):
            produits.append(
                {
                    "id": produit.id,
                    "nom": produit.nom,
                    "code_barres": produit.code_barres,
                    # "unite": produit.unite,
                }
            )

        return JsonResponse({"produits": produits})

class DashboardView(LoginRequiredMixin, View):
    template_name = 'approvisionnement/dashboard.html'
    
    def get(self, request):
        context = self.get_context_data()
        return render(request, self.template_name, context)
    
    def get_context_data(self):
        today = timezone.now().date()
        
        # Statistiques principales
        stats = {
            "besoins_en_attente": ExpressionBesoin.objects.filter(
                statut="EN_ATTENTE"
            ).count(),
            "besoins_externes_en_attente": ExpressionBesoin.objects.filter(
                statut="EN_ATTENTE", type_approvisionnement="EXTERNE"
            ).count(),
            "demandes_internes_en_attente": DemandeInterne.objects.filter(
                statut="EN_ATTENTE"
            ).count(),
            "commandes_en_cours": CommandeFournisseur.objects.filter(
                statut="EN_ATTENTE"
            ).count(),
            "livraisons_en_transit": Livraison.objects.filter(
                statut="EN_TRANSIT"
            ).count(),
            "retards": Livraison.objects.filter(
                statut="EN_TRANSIT", date_livraison_prevue__lt=today
            ).count(),
            "demandes_urgentes": DemandeInterne.objects.filter(
                besoin__priorite="URGENTE", statut__in=["EN_ATTENTE", "VALIDEE"]
            ).count(),
        }

        # Données récentes
        besoins_recents = ExpressionBesoin.objects.select_related(
            "service_demandeur"
        ).order_by("-date_creation")[:5]

        demandes_internes_recentes = DemandeInterne.objects.select_related(
            "besoin__service_demandeur", "service_destinataire"
        ).order_by("-date_creation")[:5]

        livraisons_recentes = Livraison.objects.select_related(
            "commande__fournisseur"
        ).order_by("-date_livraison_prevue")[:5]

        # Alertes
        alertes = []

        # Demandes urgentes
        demandes_urgentes = DemandeInterne.objects.filter(
            besoin__priorite="URGENTE", statut__in=["EN_ATTENTE", "VALIDEE"]
        ).count()
        if demandes_urgentes > 0:
            alertes.append(
                f"{demandes_urgentes} demande(s) interne(s) urgente(s) en attente"
            )

        # Stocks faibles - Alternative sans stock_minimum
        # Option 1: Définir un seuil fixe pour tous les produits
        SEUIL_STOCK_FAIBLE = 10

        # Calculer le stock total par produit
        from django.db.models import Sum

        stocks_faibles = (
            Stock.objects.values("produit")
            .annotate(total_quantite=Sum("quantite"))
            .filter(total_quantite__lte=SEUIL_STOCK_FAIBLE, total_quantite__gt=0)
            .count()
        )
        if stocks_faibles > 0:
            alertes.append(
                f"{stocks_faibles} produit(s) en stock faible (≤ {SEUIL_STOCK_FAIBLE} unités)"
            )

        # Stocks épuisés
        stocks_epuises = (
            Stock.objects.values("produit")
            .annotate(total_quantite=Sum("quantite"))
            .filter(total_quantite=0)
            .count()
        )
        if stocks_epuises > 0:
            alertes.append(f"{stocks_epuises} produit(s) en rupture de stock")

        # Top fournisseurs
        from django.db.models import Count, DecimalField, F, Sum
        from django.db.models.functions import Coalesce

        top_fournisseurs = (
            Fournisseur.objects.annotate(
                nb_commandes=Count("commandefournisseur"),
                # Utilisation de Coalesce pour gérer les valeurs NULL
                montant_total=Coalesce(
                    Sum(
                        F("commandefournisseur__lignes__quantite_commandee")
                        * F("commandefournisseur__lignes__prix_unitaire"),
                        output_field=DecimalField(),
                    ),
                    0,
                    output_field=DecimalField(),
                ),
            )
            .filter(nb_commandes__gt=0)
            .order_by("-montant_total")[:5]
        )

        # Données pour graphiques (derniers 30 jours)
        from datetime import timedelta

        date_debut = today - timedelta(days=30)

        chart_data = []
        for i in range(30):
            date = date_debut + timedelta(days=i)
            chart_data.append(
                {
                    "date": date.strftime("%d/%m"),
                    "besoins_externes": ExpressionBesoin.objects.filter(
                        date_creation__date=date, type_approvisionnement="EXTERNE"
                    ).count(),
                    "demandes_internes": DemandeInterne.objects.filter(
                        date_creation__date=date
                    ).count(),
                    "livraisons": Livraison.objects.filter(
                        date_reception__date=date
                    ).count(),
                }
            )

        # Ajout de statistiques supplémentaires utiles
        # Produits proches de la péremption (30 jours)
        date_limite_peremption = today + timedelta(days=30)
        produits_peremption_proche = Stock.objects.filter(
            quantite__gt=0,
            date_peremption__lte=date_limite_peremption,
            date_peremption__gte=today,
        ).count()

        if produits_peremption_proche > 0:
            alertes.append(
                f"{produits_peremption_proche} lot(s) proche(s) de la péremption (< 30 jours)"
            )

        # Produits périmés
        produits_perimes = Stock.objects.filter(
            quantite__gt=0, date_peremption__lt=today
        ).count()

        if produits_perimes > 0:
            alertes.append(f"⚠️ {produits_perimes} lot(s) périmé(s) en stock !")

        context = {
            "stats": stats,
            "besoins_recents": besoins_recents,
            "demandes_internes_recentes": demandes_internes_recentes,
            "livraisons_recentes": livraisons_recentes,
            "top_fournisseurs": top_fournisseurs,
            "alertes": alertes,
            "chart_data": chart_data,
            "produits_peremption_proche": produits_peremption_proche,
            "produits_perimes": produits_perimes,
        }

        return context


# API Views pour les stocks
class GetStockDisponibleAPIView(LoginRequiredMixin, View):
    def get(self, request, produit_id):
        try:
            produit = get_object_or_404(Produit, pk=produit_id)
            service_pharmacie = Service.objects.get(est_pharmacie=True)

            stock_disponible = Stock.objects.get_stock_disponible(
                produit=produit, service=service_pharmacie
            )

            return JsonResponse(
                {
                    "success": True,
                    "stock_disponible": stock_disponible,
                    "produit_nom": produit.nom,
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class GetStocksMultiplesAPIView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            produit_ids = data.get("produit_ids", [])

            service_pharmacie = Service.objects.get(est_pharmacie=True)
            stocks = {}

            for produit_id in produit_ids:
                try:
                    produit = Produit.objects.get(pk=produit_id)
                    stock_disponible = Stock.objects.get_stock_disponible(
                        produit=produit, service=service_pharmacie
                    )
                    stocks[produit_id] = {
                        "stock_disponible": stock_disponible,
                        "produit_nom": produit.nom,
                    }
                except Produit.DoesNotExist:
                    stocks[produit_id] = {
                        "stock_disponible": 0,
                        "produit_nom": "Produit introuvable",
                    }

            return JsonResponse({"success": True, "stocks": stocks})

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


# Dans views.py
from django.http import JsonResponse


def system_alerts_api(request):
    # Implémentation réelle à compléter
    return JsonResponse(
        {"alertes": ["3 produits en stock faible", "1 demande urgente en attente"]}
    )


def menu_stats_api(request):
    # Implémentation réelle à compléter
    return JsonResponse(
        {
            "besoins": ExpressionBesoin.objects.filter(statut="EN_ATTENTE").count(),
            "demandes": DemandeInterne.objects.filter(statut="EN_ATTENTE").count(),
            "commandes": CommandeFournisseur.objects.filter(
                statut="EN_ATTENTE"
            ).count(),
        }
    )
