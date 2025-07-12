from django.db.models import F, Q, Sum, Value
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView)
from medecin.models import Medecin
from rh.models import Personnel

from .forms import MedecinForm
from .models import Medecin


class MedecinListView(ListView):
    model = Medecin
    template_name = "medecin_list.html"
    context_object_name = "medecins"
    paginate_by = 20

    def get_queryset(self):
        return Medecin.objects.all().order_by("personnel__nom_prenom")


class MedecinCreateView(CreateView):
    form_class = MedecinForm
    model = Medecin
    template_name = "medecin_form.html"
    success_url = reverse_lazy("medecins:list")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user_queryset"] = Personnel.objects.filter(
            profil_medecin__isnull=True, statut_activite=True
        )
        return kwargs

    def form_valid(self, form):
        # Vérifie que le numéro d'ordre est unique
        numero_ordre = form.cleaned_data.get("numero_ordre")
        if Medecin.objects.filter(numero_ordre=numero_ordre).exists():
            form.add_error("numero_ordre", "Ce numéro d'ordre est déjà utilisé")
            return self.form_invalid(form)
        return super().form_valid(form)


class MedecinUpdateView(UpdateView):
    model = Medecin
    form_class = MedecinForm
    template_name = "medecin_form.html"
    success_url = reverse_lazy("medecins:list")


class MedecinDeleteView(DeleteView):
    model = Medecin
    template_name = "medecin_confirm_delete.html"
    success_url = reverse_lazy("medecins:list")

