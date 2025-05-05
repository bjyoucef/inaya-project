# pharmacies/views.py

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)

from ..models import (Produit)


class ProduitListView(LoginRequiredMixin, ListView):
    model = Produit
    template_name = "produit/produit_list.html"
    context_object_name = "produits"
    paginate_by = 20

    def get_queryset(self):
        return Produit.objects.all().order_by("nom")


class ProduitDetailView(LoginRequiredMixin, DetailView):
    model = Produit
    template_name = "produit/produit_detail.html"
    context_object_name = "produit"


class ProduitCreateView(LoginRequiredMixin, CreateView):
    model = Produit
    template_name = "produit/produit_form.html"
    fields = [
        "nom",
        "code_produit",
        "code_barres",
        "type_produit",
        "prix_achat",
        "prix_vente",
        "description",
        "est_actif",
    ]

    def get_success_url(self):
        messages.success(self.request, "Produit créé avec succès")
        return reverse_lazy("pharmacies:produit_list")


class ProduitUpdateView(LoginRequiredMixin, UpdateView):
    model = Produit
    template_name = "produit/produit_form.html"
    fields = [
        "nom",
        "code_produit",
        "code_barres",
        "type_produit",
        "prix_achat",
        "prix_vente",
        "description",
        "est_actif",
    ]

    def get_success_url(self):
        messages.success(self.request, "Produit mis à jour avec succès")
        return reverse_lazy("pharmacies:produit_detail", kwargs={"pk": self.object.pk})


class ProduitDeleteView(LoginRequiredMixin, DeleteView):
    model = Produit
    template_name = "produit/produit_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:produit_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Produit supprimé avec succès")
        return super().delete(request, *args, **kwargs)
