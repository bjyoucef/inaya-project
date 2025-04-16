from django import forms
from .models import Decharges, Payments


class DechargeForm(forms.ModelForm):
    class Meta:
        model = Decharges
        # On demande ici de renseigner uniquement les champs essentiels.
        fields = ["name", "amount", "date", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payments
        # Pour le paiement, nous demandons à l'utilisateur de sélectionner la décharge concernée et de saisir le montant.
        fields = ["id_decharge", "payment", "time_payment"]
        widgets = {
            "time_payment": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
