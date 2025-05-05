# pharmacies/views.py
from datetime import timezone

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import (CreateView, ListView)

from ..models import (Stock, Transfert)


class StockListView(LoginRequiredMixin, ListView):
    model = Stock
    template_name = "stock/stock_list.html"
    context_object_name = "stocks"

    def get_queryset(self):
        return Stock.objects.select_related("produit", "service")


class StockCreateView(LoginRequiredMixin, CreateView):
    model = Stock
    template_name = "stock/stock_form.html"
    fields = ["produit", "service", "quantite", "date_peremption", "numero_lot"]

    def form_valid(self, form):
        form.instance.date_ajout = timezone.now()
        response = super().form_valid(form)
        messages.success(self.request, "Stock ajouté avec succès")
        return response

    def get_success_url(self):
        return reverse_lazy("pharmacies:stock_list")


class TransfertListView(LoginRequiredMixin, ListView):
    model = Transfert
    template_name = "transfert/transfert_list.html"
    context_object_name = "transferts"

    def get_queryset(self):
        return Transfert.objects.select_related(
            "produit", "service_origine", "service_destination", "responsable"
        )


class TransfertCreateView(LoginRequiredMixin, CreateView):
    model = Transfert
    template_name = "transfert/transfert_form.html"
    fields = [
        "produit",
        "service_origine",
        "service_destination",
        "quantite_transferee",
        "responsable",
        "date_peremption",
        "numero_lot",
    ]

    @transaction.atomic
    def form_valid(self, form):
        try:
            with transaction.atomic():
                transfert = form.save(commit=False)
                transfert.save()
                messages.success(self.request, "Transfert effectué avec succès")
                return super().form_valid(form)
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("pharmacies:transfert_list")
