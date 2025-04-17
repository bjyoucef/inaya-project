from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import Patient
from .forms import PatientForm


# patients/views.py
class PatientListView(ListView):
    model = Patient
    template_name = "patients/patient_list.html"
    context_object_name = "patients"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PatientForm()  # Ajout du formulaire vide
        return context


# patients/views.py
class PatientCreateView(CreateView):
    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_list.html"  # Utilise le même template
    success_url = reverse_lazy("patient_list")

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class PatientUpdateView(UpdateView):
    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_form.html"
    success_url = reverse_lazy("patient_list")


class PatientDeleteView(DeleteView):
    model = Patient
    template_name = "patients/patient_confirm_delete.html"
    success_url = reverse_lazy("patient_list")
