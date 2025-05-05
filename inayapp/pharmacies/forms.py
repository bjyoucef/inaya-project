# pharmacies/forms.py
from django import forms

from rh.models import Personnel
from .models import Produit, Stock, Transfert, Achat


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "prix_achat": forms.NumberInput(attrs={"step": "0.01"}),
            "prix_vente": forms.NumberInput(attrs={"step": "0.01"}),
        }


class StockForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ["produit", "service", "quantite", "date_peremption", "numero_lot"]


class TransfertForm(forms.ModelForm):
    class Meta:
        model = Transfert
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["responsable"].queryset = Personnel.objects.filter(
                service=user.service
            )


class AchatForm(forms.ModelForm):
    class Meta:
        model = Achat
        fields = [
            "produit",
            "service_destination",
            "fournisseur",
            "quantite_achetee",
            "prix_unitaire",
            "numero_lot",
            "date_peremption",
        ]
        widgets = {
            "date_peremption": forms.DateInput(attrs={"type": "date"}),
            "prix_unitaire": forms.NumberInput(attrs={"step": "0.01"}),
        }


# fournisseurs/forms.py
from django import forms
from .models import Fournisseur, HistoriquePaiement


class FournisseurForm(forms.ModelForm):
    class Meta:
        model = Fournisseur
        exclude = ["solde"]
        widgets = {
            "adresse": forms.Textarea(attrs={"rows": 3}),
            "conditions_paiement": forms.NumberInput(attrs={"min": 0}),
            "limite_credit": forms.NumberInput(attrs={"step": "0.01"}),
        }


class PaiementForm(forms.ModelForm):
    class Meta:
        model = HistoriquePaiement
        fields = ["montant", "mode_paiement", "reference", "statut", "notes"]
        widgets = {
            "date_paiement": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "montant": forms.NumberInput(attrs={"step": "0.01"}),
        }
