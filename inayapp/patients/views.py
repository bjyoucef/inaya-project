from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import Patient


class PatientListView(ListView):
    model = Patient
    template_name = "patient_list.html"
    context_object_name = "patients"
    paginate_by = 20  # ajustez selon vos besoins

    def get_queryset(self):
        return Patient.objects.filter(is_active=True).order_by("last_name")


class PatientCreateView(CreateView):
    model = Patient
    template_name = "patient_form.html"
    fields = [
        "first_name",
        "last_name",
        "date_of_birth",
        "place_of_birth",
        "social_security_number",
        "nom_de_assure",
        "securite_sociale",
        "gender",
        "phone_number",
        "email",
        "address",
    ]
    success_url = reverse_lazy("patients:list")

    def form_valid(self, form):
        form.instance.id_created_par = self.request.user.personnel
        return super().form_valid(form)


class PatientUpdateView(UpdateView):
    model = Patient
    template_name = "patient_form.html"
    fields = PatientCreateView.fields
    success_url = reverse_lazy("patients:list")

    def form_valid(self, form):
        form.instance.id_updated_par = self.request.user.personnel
        return super().form_valid(form)


class PatientDeleteView(DeleteView):
    model = Patient
    template_name = "patient_confirm_delete.html"
    success_url = reverse_lazy("patients:list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.delete()  # override soft-delete
        return super().form_valid(form=None)
