from django import forms
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from medical.models import Service
from .models import Medecin
from rh.models import Personnel


class MedecinForm(forms.ModelForm):
    class Meta:
        model = Medecin
        fields = [
            "personnel",
            "services",
            "specialite",
            "numero_ordre",
            "photo_profil",
            "disponible",
        ]
        widgets = {
            # On utilise un SelectMultiple vanilla, Choices.js se chargera du multi-select
            "services": forms.SelectMultiple(
                attrs={
                    "class": "form-select choices-multiple",
                    "data-placeholder": "Rechercher un service...",
                }
            ),
            "personnel": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        user_queryset = kwargs.pop("user_queryset", None)
        super().__init__(*args, **kwargs)
        if user_queryset is not None:
            self.fields["personnel"].queryset = user_queryset

    def clean_numero_ordre(self):
        numero = self.cleaned_data.get("numero_ordre")
        qs = Medecin.objects.filter(numero_ordre=numero)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ce numéro d'ordre est déjà utilisé.")
        return numero
