# pharmacies/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from ..models import Produit
from ..forms.ph_forms import ProduitForm, ProduitSearchForm


class ProduitListView(LoginRequiredMixin, ListView):
    """Vue liste des produits avec recherche et filtrage"""


    model = Produit
    template_name = "produit/produit_list.html"
    context_object_name = "produits"
    paginate_by = 25

    def get_queryset(self):
        """Filtrage et recherche des produits"""
        queryset = Produit.objects.avec_marge_beneficiaire()

        # Récupération des paramètres de recherche
        form = ProduitSearchForm(self.request.GET)

        if form.is_valid():
            nom = form.cleaned_data.get("nom")
            code_produit = form.cleaned_data.get("code_produit")
            type_produit = form.cleaned_data.get("type_produit")
            # est_actif = form.cleaned_data.get("est_actif")
            prix_min = form.cleaned_data.get("prix_min")
            prix_max = form.cleaned_data.get("prix_max")

            # Filtrage par nom (recherche insensible à la casse)
            if nom:
                queryset = queryset.filter(
                    Q(nom__icontains=nom) | Q(description__icontains=nom)
                )

            # Filtrage par code produit
            if code_produit:
                queryset = queryset.filter(code_produit__icontains=code_produit)

            # Filtrage par type de produit
            if type_produit:
                queryset = queryset.filter(type_produit=type_produit)

            # # Filtrage par statut actif
            # if est_actif == "true":
            #     queryset = queryset.filter(est_actif=True)
            # elif est_actif == "false":
            #     queryset = queryset.filter(est_actif=False)

            # Filtrage par prix
            if prix_min:
                queryset = queryset.filter(prix_vente__gte=prix_min)
            if prix_max:
                queryset = queryset.filter(prix_vente__lte=prix_max)

        # Tri par défaut
        return queryset.order_by("nom")

    def get_context_data(self, **kwargs):
        """Ajout du formulaire de recherche au contexte"""
        context = super().get_context_data(**kwargs)
        context["search_form"] = ProduitSearchForm(self.request.GET)

        # Statistiques pour le dashboard
        context["stats"] = {
            "total_produits": Produit.objects.count(),
            "produits_actifs": Produit.objects.actifs().count(),
            "medicaments": Produit.objects.medicaments().count(),
            "consommables": Produit.objects.consommables().count(),
        }

        return context


class ProduitDetailView(LoginRequiredMixin, DetailView):
    """Vue détail d'un produit"""

    model = Produit
    template_name = "produit/produit_detail.html"
    context_object_name = "produit"

    def get_object(self):
        """Récupération de l'objet avec calculs de marge"""
        return get_object_or_404(
            Produit.objects.avec_marge_beneficiaire(), pk=self.kwargs["pk"]
        )


class ProduitCreateView(LoginRequiredMixin, CreateView):
    """Vue création d'un produit"""

    model = Produit
    form_class = ProduitForm
    template_name = "produit/produit_form.html"

    def form_valid(self, form):
        """Traitement après validation du formulaire"""
        response = super().form_valid(form)
        messages.success(
            self.request, f"Le produit '{self.object.nom}' a été créé avec succès."
        )
        return response

    def get_success_url(self):
        """Redirection après création réussie"""
        return reverse_lazy("pharmacies:produit_detail", kwargs={"pk": self.object.pk})


class ProduitUpdateView(LoginRequiredMixin, UpdateView):
    """Vue modification d'un produit"""

    model = Produit
    form_class = ProduitForm
    template_name = "produit/produit_form.html"

    def form_valid(self, form):
        """Traitement après validation du formulaire"""
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Le produit '{self.object.nom}' a été mis à jour avec succès.",
        )
        return response

    def get_success_url(self):
        """Redirection après modification réussie"""
        return reverse_lazy("pharmacies:produit_detail", kwargs={"pk": self.object.pk})


class ProduitDeleteView(LoginRequiredMixin, DeleteView):
    """Vue suppression d'un produit"""

    model = Produit
    template_name = "produit/produit_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:produit_list")

    def delete(self, request, *args, **kwargs):
        """Traitement de la suppression avec message"""
        produit_nom = self.get_object().nom
        response = super().delete(request, *args, **kwargs)
        messages.success(
            request, f"Le produit '{produit_nom}' a été supprimé avec succès."
        )
        return response


# Vue AJAX pour l'autocomplétion (optionnelle)
class ProduitAutocompleteView(LoginRequiredMixin, ListView):
    """Vue AJAX pour l'autocomplétion des produits"""

    def get(self, request, *args, **kwargs):
        """Retourne les produits correspondant à la recherche en JSON"""
        query = request.GET.get("q", "")

        if len(query) < 2:
            return JsonResponse({"results": []})

        produits = Produit.objects.actifs().filter(
            Q(nom__icontains=query) | Q(code_produit__icontains=query)
        )[:10]

        results = [
            {
                "id": produit.id,
                "text": f"{produit.code_produit} - {produit.nom}",
                "prix_vente": str(produit.prix_vente),
            }
            for produit in produits
        ]

        return JsonResponse({"results": results})
