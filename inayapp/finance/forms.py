from django import forms
from django.core.validators import MinValueValidator
from .models import Decharges, Payments


class DechargeForm(forms.ModelForm):
    class Meta:
        model = Decharges
        fields = [
            "name",
            "amount",
            "date",
            "note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payments
        fields = ["payment"]
        widgets = {
            "payment": forms.NumberInput(
                attrs={"step": "1.00", "min": "1.00", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment"].validators.append(
            MinValueValidator(0.01, "Le montant doit être supérieur à 0")
        )


# finance/forms.py
from django import forms
from .models import BonDePaiement


class BonDePaiementForm(forms.ModelForm):
    class Meta:
        model = BonDePaiement
        fields = ["montant", "methode"]
        widgets = {"montant": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"})}
