# pharmacies/views.py
from io import BytesIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)
from reportlab.pdfgen import canvas

from ..models import (BonCommande, BonLivraison, LigneCommande)

LigneCommandeFormSet = inlineformset_factory(
    BonCommande,
    LigneCommande,
    fields=("produit", "quantite", "prix_unitaire", "date_peremption", "numero_lot"),
    extra=3,
)


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


class BonCommandeCreateView(LoginRequiredMixin, CreateView):
    model = BonCommande
    fields = [
        "fournisseur",
        "service_destination",
        "date_livraison_prevue",
        "commentaire",
    ]
    template_name = "commandes/commande_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["formset"] = LigneCommandeFormSet(self.request.POST)
        else:
            context["formset"] = LigneCommandeFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["formset"]
        if formset.is_valid():
            self.object = form.save(commit=False)
            self.object.utilisateur = self.request.user
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse_lazy("pharmacies:commande_detail", kwargs={"pk": self.object.pk})


class BonCommandeDetailView(LoginRequiredMixin, DetailView):
    model = BonCommande
    template_name = "commandes/commande_detail.html"


class ValiderLivraisonView(LoginRequiredMixin, UpdateView):
    model = BonLivraison
    fields = []
    template_name = "commandes/valider_livraison.html"

    def form_valid(self, form):
        livraison = form.save(commit=False)
        livraison.est_complet = True
        livraison.save()
        return super().form_valid(form)


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

    def get_success_url(self):
        return reverse_lazy("pharmacies:commande_detail", kwargs={"pk": self.object.pk})


class BonCommandeDeleteView(LoginRequiredMixin, DeleteView):
    model = BonCommande
    template_name = "commandes/commande_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:commande_list")


class BonLivraisonCreateView(LoginRequiredMixin, CreateView):
    model = BonLivraison
    fields = ["numero_bl", "date_livraison", "fichier_bl"]
    template_name = "commandes/livraison_form.html"

    def form_valid(self, form):
        form.instance.commande_id = self.kwargs["commande_pk"]
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "pharmacies:commande_detail", kwargs={"pk": self.kwargs["commande_pk"]}
        )


class GenererPDFCommandeView(LoginRequiredMixin, DetailView):
    model = BonCommande
    template_name = "commandes/commande_pdf.html"

    def get(self, request, *args, **kwargs):
        # Création du PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer)

        # Configuration du document
        p.setFont("Helvetica", 12)
        commande = self.get_object()

        # Contenu du PDF
        p.drawString(100, 800, f"Bon de commande n°{commande.numero_commande}")
        p.drawString(100, 780, f"Fournisseur: {commande.fournisseur.raison_sociale}")
        p.drawString(100, 760, f"Date: {commande.date_commande.strftime('%d/%m/%Y')}")

        y = 740
        for ligne in commande.lignes.all():
            p.drawString(
                100,
                y,
                f"- {ligne.produit.nom} : {ligne.quantite} x {ligne.prix_unitaire}€",
            )
            y -= 20

        p.showPage()
        p.save()

        buffer.seek(0)
        return HttpResponse(buffer, content_type="application/pdf")
