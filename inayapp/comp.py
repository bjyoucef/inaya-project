# forms.py
from django import forms
from django.core.validators import MinValueValidator


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payments
        fields = ["payment"]
        widgets = {
            "payment": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment"].validators.append(
            MinValueValidator(0.01, "Le montant doit être supérieur à 0")
        )
