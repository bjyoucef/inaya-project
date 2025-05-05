# pharmacies/views.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)

from ..forms import FournisseurForm, PaiementForm
from ..models import (Fournisseur,
                     HistoriquePaiement, OrdrePaiement)


class FournisseurListView(LoginRequiredMixin, ListView):
    model = Fournisseur
    template_name = "fournisseurs/liste.html"
    context_object_name = "fournisseurs"
    paginate_by = 20
    ordering = ["-date_creation"]

    def get_queryset(self):
        return Fournisseur.objects.order_by("-date_creation")


class FournisseurCreateView(LoginRequiredMixin, CreateView):
    model = Fournisseur
    form_class = FournisseurForm
    template_name = "fournisseurs/form.html"
    success_url = reverse_lazy("pharmacies:liste")

    def form_valid(self, form):
        form.instance.utilisateur_creation = self.request.user
        return super().form_valid(form)


class FournisseurDetailView(LoginRequiredMixin, DetailView):
    model = Fournisseur
    template_name = "fournisseurs/detail.html"
    context_object_name = "fournisseur"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["paiements"] = self.object.historique_paiements.select_related("achat")
        return context


class FournisseurUpdateView(LoginRequiredMixin, UpdateView):
    model = Fournisseur
    form_class = FournisseurForm
    template_name = "fournisseurs/form.html"
    success_url = reverse_lazy("pharmacies:liste")


class FournisseurDeleteView(LoginRequiredMixin, DeleteView):
    model = Fournisseur
    template_name = "fournisseurs/supprimer.html"
    success_url = reverse_lazy("pharmacies:liste")


class PaiementCreateView(LoginRequiredMixin, CreateView):
    model = HistoriquePaiement
    form_class = PaiementForm
    template_name = "fournisseurs/paiement_form.html"

    def get_initial(self):
        return {"fournisseur": self.kwargs["pk"]}

    def form_valid(self, form):
        form.instance.fournisseur_id = self.kwargs["pk"]
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("pharmacies:detail", kwargs={"pk": self.kwargs["pk"]})


class OrdrePaiementCreateView(LoginRequiredMixin, CreateView):
    model = OrdrePaiement
    fields = ["montant", "mode_paiement", "date_paiement", "preuve"]
    template_name = "commandes/paiement_form.html"

    def form_valid(self, form):
        form.instance.commande_id = self.kwargs["commande_pk"]
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "pharmacies:commande_detail", kwargs={"pk": self.kwargs["commande_pk"]}
        )


class AnnulerPaiementView(LoginRequiredMixin, UpdateView):
    model = OrdrePaiement
    fields = []
    template_name = "commandes/annuler_paiement.html"

    def form_valid(self, form):
        paiement = form.save(commit=False)
        paiement.statut = "ANNULE"
        paiement.save()
        paiement.commande.fournisseur.mettre_a_jour_solde(
            paiement.montant, operation="ajout"
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "pharmacies:commande_detail", kwargs={"pk": self.object.commande.pk}
        )
