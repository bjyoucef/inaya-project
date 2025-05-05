# pharmacies/views.py
from django.contrib import messages
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic import ListView, DetailView
from .forms import ProduitForm, StockForm, TransfertForm, AchatForm
from .models import Produit, Stock, Transfert, Achat


class ProduitListView(ListView):
    model = Produit
    template_name = "produit/produit_list.html"
    context_object_name = "produits"
    paginate_by = 20


class ProduitDetailView(DetailView):
    model = Produit
    template_name = "produit/produit_detail.html"


class ProduitCreateView(CreateView):
    model = Produit
    form_class = ProduitForm
    template_name = "produit/produit_form.html"

    def get_success_url(self):
        messages.success(self.request, "Produit créé avec succès")
        return reverse_lazy("pharmacies:produit_list")


class ProduitUpdateView(UpdateView):
    model = Produit
    form_class = ProduitForm
    template_name = "produit/produit_form.html"

    def get_success_url(self):
        messages.success(self.request, "Produit mis à jour avec succès")
        return reverse_lazy("pharmacies:produit_detail", kwargs={"pk": self.object.pk})


class ProduitDeleteView(DeleteView):
    model = Produit
    template_name = "produit/produit_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:produit_list")


class StockCreateView(CreateView):
    model = Stock
    form_class = StockForm
    template_name = "stock/stock_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Stock ajouté avec succès")
        return response


class TransfertCreateView(CreateView):
    model = Transfert
    form_class = TransfertForm
    template_name = "transfert/transfert_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class AchatCreateView(CreateView):
    model = Achat
    form_class = AchatForm
    template_name = "achat/form.html"
