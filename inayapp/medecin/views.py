from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import Medecin
from rh.models import Personnel
from .forms import MedecinForm

class MedecinListView(ListView):
    model = Medecin
    template_name = "medecins/medecin_list.html"
    context_object_name = "medecins"
    paginate_by = 20

    def get_queryset(self):
        return Medecin.objects.all().order_by("personnel__user__last_name")


class MedecinCreateView(CreateView):
    form_class = MedecinForm
    model = Medecin
    template_name = "medecins/medecin_form.html"
    success_url = reverse_lazy("medecins:list")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user_queryset"] = Personnel.objects.filter(
            profil_medecin__isnull=True, statut_activite=True
        ).select_related("user")
        return kwargs

    def form_valid(self, form):
        # Vérifie que le numéro d'ordre est unique
        numero_ordre = form.cleaned_data.get("numero_ordre")
        if Medecin.objects.filter(numero_ordre=numero_ordre).exists():
            form.add_error("numero_ordre", "Ce numéro d'ordre est déjà utilisé")
            return self.form_invalid(form)
        return super().form_valid(form)


class MedecinUpdateView(UpdateView):
    form_class = MedecinForm
    template_name = "medecins/medecin_form.html"
    success_url = reverse_lazy("medecins:list")


class MedecinDeleteView(DeleteView):
    model = Medecin
    template_name = "medecins/medecin_confirm_delete.html"
    success_url = reverse_lazy("medecins:list")
