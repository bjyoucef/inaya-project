# medecin/forms.py
from django import forms
from .models import Medecin
from rh.models import Personnel


class MedecinForm(forms.ModelForm):
    # Champs pour création d'un nouveau Personnel
    first_name = forms.CharField(
        max_length=30, required=False, label="Prénom du médecin"
    )
    last_name = forms.CharField(max_length=30, required=False, label="Nom du médecin")

    class Meta:
        model = Medecin
        fields = [
            "personnel",
            "first_name",
            "last_name",
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

    def clean(self):
        cleaned = super().clean()
        personnel = cleaned.get("personnel")
        first = cleaned.get("first_name")
        last = cleaned.get("last_name")

        # vérifier qu'on a bien l'un ou l'autre
        if not personnel and not (first and last):
            raise forms.ValidationError(
                "Vous devez soit sélectionner un personnel existant, "
                "soit saisir le prénom et le nom du médecin."
            )
        return cleaned

    def save(self, commit=True):
        # Si on n'a pas de personnel sélectionné, on en crée un
        personnel = self.cleaned_data.get("personnel")
        if not personnel:
            first = self.cleaned_data["first_name"]
            last = self.cleaned_data["last_name"]
            # Créer le Personnel (on pourrait aussi créer un User, etc.)
            personnel = Personnel.objects.create(nom_prenom=f"{last} {first}")
        # On associe ce personnel au Medecin
        self.instance.personnel = personnel
        return super().save(commit=commit)
