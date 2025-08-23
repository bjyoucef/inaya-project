# pharmacies/forms/approvisionnement_interne.py

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from medical.models.services import Service

from ..models.produit import Produit
from ..models.approvisionnement_interne import DemandeInterne, LigneDemandeInterne


class DemandeInterneForm(forms.ModelForm):
    """Formulaire de création/modification d'une demande interne"""

    class Meta:
        model = DemandeInterne
        fields = [
            "service_demandeur",
            "pharmacie",
            "priorite",
            "motif_demande",
            "observations",
        ]
        widgets = {
            "service_demandeur": forms.Select(
                attrs={"class": "form-select", "required": True}
            ),
            "pharmacie": forms.Select(attrs={"class": "form-select", "required": True}),
            "priorite": forms.Select(attrs={"class": "form-select", "required": True}),
            "motif_demande": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Motif de la demande...",
                }
            ),
            "observations": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Observations (optionnel)...",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Limiter les choix selon l'utilisateur
        if user:
            # Si l'utilisateur appartient à un service, pré-sélectionner
            if hasattr(user, "service"):
                self.fields["service_demandeur"].initial = user.service
                # Si ce n'est pas une pharmacie, masquer le champ
                if user.service.type_service != "PHARMACIE":
                    self.fields["service_demandeur"].widget = forms.HiddenInput()

        # Limiter aux pharmacies actives
        self.fields["pharmacie"].queryset = Service.objects.filter(
            type_service="PHARMACIE", est_actif=True
        )

        # Limiter aux services actifs (non pharmacies)
        self.fields["service_demandeur"].queryset = Service.objects.filter(
            est_actif=True
        ).exclude(type_service="PHARMACIE")

    def clean(self):
        cleaned_data = super().clean()
        service_demandeur = cleaned_data.get("service_demandeur")
        pharmacie = cleaned_data.get("pharmacie")

        # Vérifications
        if service_demandeur == pharmacie:
            raise ValidationError("Le service demandeur ne peut pas être la pharmacie")

        if pharmacie and pharmacie.type_service != "PHARMACIE":
            raise ValidationError("Le service approvisionneur doit être une pharmacie")

        return cleaned_data


class LigneDemandeInterneForm(forms.ModelForm):
    """Formulaire pour une ligne de demande interne"""

    class Meta:
        model = LigneDemandeInterne
        fields = ["produit", "quantite_demandee", "observations"]
        widgets = {
            "produit": forms.Select(
                attrs={"class": "form-select select2", "required": True}
            ),
            "quantite_demandee": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "required": True}
            ),
            "observations": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Observations..."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limiter aux produits actifs
        self.fields["produit"].queryset = Produit.objects.filter(est_actif=True)


# FormSet pour les lignes
LigneDemandeInterneFormSet = inlineformset_factory(
    DemandeInterne,
    LigneDemandeInterne,
    form=LigneDemandeInterneForm,
    fields=["produit", "quantite_demandee", "observations"],
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
    error_messages={"too_few_forms": "Au moins un produit doit être demandé."},
)


class DemandeInterneValidationForm(forms.Form):
    """Formulaire de validation d'une demande interne"""

    action = forms.ChoiceField(
        choices=[("valider", "Valider"), ("rejeter", "Rejeter")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    motif_rejet = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Motif du rejet (obligatoire si rejet)...",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        motif_rejet = cleaned_data.get("motif_rejet")

        if action == "rejeter" and not motif_rejet:
            raise ValidationError("Le motif du rejet est obligatoire")

        return cleaned_data


class LigneValidationForm(forms.Form):
    """Formulaire pour valider une ligne de demande"""

    ligne_id = forms.IntegerField(widget=forms.HiddenInput())

    produit_nom = forms.CharField(
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control-plaintext", "readonly": True}
        ),
    )

    quantite_demandee = forms.IntegerField(
        disabled=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control-plaintext", "readonly": True}
        ),
    )

    stock_disponible = forms.IntegerField(
        disabled=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control-plaintext", "readonly": True}
        ),
    )

    quantite_accordee = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    def __init__(self, *args, ligne=None, stock_disponible=0, **kwargs):
        super().__init__(*args, **kwargs)

        if ligne:
            self.fields["ligne_id"].initial = ligne.id
            self.fields["produit_nom"].initial = ligne.produit.nom
            self.fields["quantite_demandee"].initial = ligne.quantite_demandee
            self.fields["stock_disponible"].initial = stock_disponible
            self.fields["quantite_accordee"].initial = min(
                ligne.quantite_demandee, stock_disponible
            )
            self.fields["quantite_accordee"].widget.attrs["max"] = min(
                ligne.quantite_demandee, stock_disponible
            )

    def clean_quantite_accordee(self):
        quantite = self.cleaned_data["quantite_accordee"]
        stock = self.initial.get("stock_disponible", 0)
        demande = self.initial.get("quantite_demandee", 0)

        if quantite > stock:
            raise ValidationError(
                f"La quantité accordée ne peut pas dépasser le stock disponible ({stock})"
            )

        if quantite > demande:
            raise ValidationError(
                f"La quantité accordée ne peut pas dépasser la quantité demandée ({demande})"
            )

        return quantite


class FiltreDemandeInterneForm(forms.Form):
    """Formulaire de filtrage des demandes internes"""

    statut = forms.ChoiceField(
        choices=[("", "Tous les statuts")] + DemandeInterne.STATUT_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    priorite = forms.ChoiceField(
        choices=[("", "Toutes les priorités")] + DemandeInterne.PRIORITE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(est_actif=True),
        required=False,
        empty_label="Tous les services",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"class": "form-control form-control-sm", "type": "date"}
        ),
    )

    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"class": "form-control form-control-sm", "type": "date"}
        ),
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Rechercher...",
            }
        ),
    )


class DemandeInterneRapideForm(forms.Form):
    """Formulaire pour création rapide d'une demande"""

    produit = forms.ModelChoiceField(
        queryset=Produit.objects.filter(est_actif=True),
        widget=forms.Select(attrs={"class": "form-select", "required": True}),
    )

    quantite = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "1",
                "required": True,
                "placeholder": "Quantité",
            }
        ),
    )

    priorite = forms.ChoiceField(
        choices=DemandeInterne.PRIORITE_CHOICES,
        initial="NORMALE",
        widget=forms.Select(attrs={"class": "form-select", "required": True}),
    )

    motif = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Motif (optionnel)...",
            }
        ),
    )
