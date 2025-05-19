# pharmacies/views.py
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import File
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from ..forms import BonLivraisonForm, LigneCommandeFormSet
from ..models import Achat, BonCommande, BonLivraison, LigneCommande
from ..utils import generate_bl_pdf


class BonCommandeListView(LoginRequiredMixin, ListView):
    model = BonCommande
    template_name = "commandes/commande_list.html"
    context_object_name = "commandes"
    paginate_by = 20

    def get_queryset(self):
        return BonCommande.objects.select_related(
            "fournisseur", "service_destination"
        ).order_by("-date_commande")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ajouter des statistiques ou des filtres supplémentaires si nécessaire
        return context


class BonCommandeDetailView(LoginRequiredMixin, DetailView):
    model = BonCommande
    template_name = "commandes/commande_detail.html"


class BonCommandeCreateView(LoginRequiredMixin, CreateView):
    model = BonCommande
    fields = [
        "fournisseur",
        "service_destination",
        "date_livraison_prevue",
        "statut",
        "commentaire",
    ]
    template_name = "commandes/commande_form.html"

    def get_context_data(self, **kwargs):
        """
        Toujours injecter un formset :
        - Si on en passe un explicitement (en cas de POST invalide), on l'utilise.
        - Sinon, on le construit à partir de POST (pour pouvoir ré-afficher les données en cas d'erreur).
        - Sinon (GET), on renvoie juste le formset vide avec extra=1.
        """
        ctx = super().get_context_data(**kwargs)

        if "formset" in kwargs:
            ctx["formset"] = kwargs["formset"]
        elif self.request.method == "POST":
            # On lie au POST (sans instance pour l'instant, instance créée après save)
            ctx["formset"] = LigneCommandeFormSet(self.request.POST)
        else:
            # GET : affichage initial, Django génère 1 form vide grâce à extra=1
            ctx["formset"] = LigneCommandeFormSet()

        return ctx

    @transaction.atomic
    def form_valid(self, form):
        # 1) Sauvegarde de la commande pour obtenir un PK
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        # 2) Reconstruction du formset, cette fois lié à l'instance
        formset = LigneCommandeFormSet(self.request.POST, instance=self.object)
        
        if not formset.is_valid():
            print("Formset errors:", formset.errors)  # Debug logging
    
        if formset.is_valid():
            formset.save()
            messages.success(self.request, "Bon de commande créé avec succès")
            return redirect(self.object.get_absolute_url())

        # 3) En cas d'erreur sur le formset, on repasse dans le template
        messages.error(self.request, "Veuillez corriger les erreurs ci-dessous")
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def get_success_url(self):
        return self.object.get_absolute_url()


class BonCommandeUpdateView(LoginRequiredMixin, UpdateView):
    model = BonCommande
    fields = [
        "fournisseur",
        "service_destination",
        "date_livraison_prevue",
        "commentaire",
        "statut",
    ]
    template_name = "commandes/commande_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["formset"] = LigneCommandeFormSet(
                self.request.POST, instance=self.object
            )
        else:
            ctx["formset"] = LigneCommandeFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["formset"]
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(self.request, "Bon de commande modifié avec succès")
            return redirect(self.object.get_absolute_url())
        messages.error(self.request, "Veuillez corriger les erreurs du formulaire")
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse_lazy("pharmacies:commande_detail", kwargs={"pk": self.object.pk})


class BonCommandeDeleteView(LoginRequiredMixin, DeleteView):
    model = BonCommande
    template_name = "commandes/commande_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:commande_list")


# pharmacies/views.py
class BonCommandeUpdateStatutView(LoginRequiredMixin, UpdateView):
    model = BonCommande
    fields = ["statut"]
    http_method_names = ["post"]

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Statut mis à jour avec succès")
        return redirect("pharmacies:commande_list")

    def form_invalid(self, form):
        messages.error(self.request, "Erreur lors du changement de statut")
        return redirect("pharmacies:commande_list")


class BonLivraisonCreateView(LoginRequiredMixin, CreateView):
    model = BonLivraison
    form_class = BonLivraisonForm
    template_name = "commandes/livraison_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["commande_pk"] = self.kwargs["commande_pk"]
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["commande"] = BonCommande.objects.get(pk=self.kwargs["commande_pk"])
        return context

    @transaction.atomic
    def form_valid(self, form):
        commande = BonCommande.objects.get(pk=self.kwargs["commande_pk"])

        if commande.statut not in ["VALIDE", "LIVRE"]:
            messages.error(
                self.request, "Statut de commande invalide pour une livraison"
            )
            return redirect(commande.get_absolute_url())

        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # Génération automatique du PDF
        pdf_buffer = generate_bl_pdf(self.object)
        self.object.fichier_bl.save(f"BL_{self.object.numero_bl}.pdf", File(pdf_buffer))
        self.object.save()

        messages.success(self.request, "Bon de livraison créé avec succès")
        return response

    def get_success_url(self):
        return reverse(
            "pharmacies:commande_detail", kwargs={"pk": self.kwargs["commande_pk"]}
        )


class ValiderLivraisonView(LoginRequiredMixin, UpdateView):
    model = BonLivraison
    fields = []
    template_name = "commandes/livraison_valider.html"

    @transaction.atomic
    def form_valid(self, form):
        livraison = form.save(commit=False)
        if not livraison.est_complet:
            livraison.mettre_a_jour_stock()
            messages.success(self.request, "Livraison validée et stock mis à jour")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pharmacies:livraison_detail", kwargs={"pk": self.object.pk})


# pharmacies/views.py
class BonLivraisonListView(LoginRequiredMixin, ListView):
    model = BonLivraison
    template_name = "commandes/livraison_list.html"
    context_object_name = "livraisons"
    paginate_by = 20

    def get_queryset(self):
        return BonLivraison.objects.select_related("commande").order_by(
            "-date_livraison"
        )


# pharmacies/views.py
class BonLivraisonDetailView(LoginRequiredMixin, DetailView):
    model = BonLivraison
    template_name = "commandes/livraison_detail.html"
    context_object_name = "livraison"


class GenererPDFCommandeView(LoginRequiredMixin, DetailView):
    model = BonCommande
    template_name = "commandes/commande_pdf.html"

    def get(self, request, *args, **kwargs):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        commande = self.get_object()

        # En-tête
        elements.append(
            Paragraph(f"Bon de Commande N°{commande.numero_commande}", styles["Title"])
        )
        elements.append(
            Paragraph(
                f"Date: {commande.date_commande.strftime('%d/%m/%Y')}", styles["Normal"]
            )
        )
        elements.append(
            Paragraph(
                f"Fournisseur: {commande.fournisseur.raison_sociale}", styles["Normal"]
            )
        )

        # Tableau des articles
        data = [["Produit", "Quantité", "Prix Unitaire", "Total"]]
        for ligne in commande.lignes.all():
            data.append(
                [
                    ligne.produit.nom,
                    str(ligne.quantite),
                    f"{ligne.prix_unitaire} €",
                    f"{ligne.montant} €",
                ]
            )

        table = Table(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        elements.append(table)

        # Total
        elements.append(
            Paragraph(f"Total Général: {commande.montant_total} €", styles["Heading2"])
        )

        doc.build(elements)
        buffer.seek(0)
        return HttpResponse(buffer, content_type="application/pdf")
