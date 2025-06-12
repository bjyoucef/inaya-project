# pharmacies/views/views_fournisseur.py

import logging

from django.contrib import messages
from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        PermissionRequiredMixin)
from django.db import transaction
from django.forms import modelform_factory
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)
from openpyxl import Workbook

from ..forms import FournisseurForm, OrdrePaiementForm
from ..models import Fournisseur, OrdrePaiement

logger = logging.getLogger(__name__)

class FournisseurListView(PermissionRequiredMixin, ListView):
    permission_required = "pharmacies.view_fournisseur"
    model = Fournisseur
    template_name = "fournisseurs/liste.html"
    context_object_name = "fournisseurs"
    paginate_by = 25
    ordering = ["-date_creation"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.GET.get("q"):
            qs = qs.filter(raison_sociale__icontains=self.request.GET["q"])
        return qs


class FournisseurCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "pharmacies.add_fournisseur"
    model = Fournisseur
    form_class = FournisseurForm
    template_name = "fournisseurs/form.html"
    success_url = reverse_lazy("pharmacies:liste")

    def get_initial(self):
        return {"pays": "Algérie", "conditions_paiement": 30}

    @transaction.atomic
    def form_valid(self, form):
        form.instance.utilisateur_creation = self.request.user
        messages.success(self.request, "Fournisseur créé avec succès")
        return super().form_valid(form)


class FournisseurDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "pharmacies.view_fournisseur"
    model = Fournisseur
    template_name = "fournisseurs/detail.html"
    context_object_name = "fournisseur"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Retirez les références à historique_paiements
        context["paiement_form"] = None  # Si vous aviez un formulaire lié
        return context


class FournisseurUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "pharmacies.change_fournisseur"
    model = Fournisseur
    form_class = FournisseurForm
    template_name = "fournisseurs/form.html"

    def get_success_url(self):
        return reverse_lazy("pharmacies:detail", kwargs={"pk": self.object.pk})

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, "Modifications enregistrées")
        return super().form_valid(form)


class FournisseurDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "pharmacies.delete_fournisseur"
    model = Fournisseur
    template_name = "fournisseurs/supprimer.html"
    success_url = reverse_lazy("pharmacies:liste")

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        messages.success(request, "Fournisseur supprimé")
        return response


# pharmacies/views.py
class OrdrePaiementCreateView(CreateView):
    model = OrdrePaiement
    form_class = OrdrePaiementForm
    template_name = "pharmacies/ordre_paiement_form.html"
    success_url = reverse_lazy("ordre-paiement-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fournisseurs"] = Fournisseur.objects.active()
        return context


class OrdrePaiementUpdateView(UpdateView):
    model = OrdrePaiement
    form_class = OrdrePaiementForm
    template_name = "pharmacies/ordre_paiement_form.html"
    success_url = reverse_lazy("ordre-paiement-list")
