# pharmacies/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from ..models.stock import AjustementStock
from rh.models import Personnel
from django import forms
from medical.models import Service
from rh.models import Personnel
from ..models import (Fournisseur
                     , Produit, Stock)


class ProduitForm(forms.ModelForm):
    """Formulaire pour créer et modifier un produit"""

    class Meta:
        model = Produit
        fields = [
            "nom",
            "code_produit",
            "code_barres",
            "type_produit",
            "prix_achat",
            "prix_vente",
            # "description",
            # "est_actif",
        ]
        widgets = {
            "nom": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nom du produit"}
            ),
            "code_produit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Code unique du produit"}
            ),
            "code_barres": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Code-barres (optionnel)",
                }
            ),
            "type_produit": forms.Select(attrs={"class": "form-select"}),
            "prix_achat": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "placeholder": "0.00",
                }
            ),
            "prix_vente": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "placeholder": "0.00",
                }
            ),

        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ajouter des labels et help_text personnalisés
        self.fields["nom"].label = "Nom du produit *"
        self.fields["code_produit"].label = "Code produit *"
        self.fields["code_barres"].label = "Code-barres"
        self.fields["type_produit"].label = "Type de produit *"
        self.fields["prix_achat"].label = "Prix d'achat (€) *"
        self.fields["prix_vente"].label = "Prix de vente (€) *"
        # self.fields["description"].label = "Description"
        # self.fields["est_actif"].label = "Produit actif"

        # Marquer les champs requis
        for field_name, field in self.fields.items():
            if field.required:
                field.widget.attrs["required"] = True

    def clean(self):
        """Validation personnalisée du formulaire"""
        cleaned_data = super().clean()
        prix_achat = cleaned_data.get("prix_achat")
        prix_vente = cleaned_data.get("prix_vente")

        if prix_achat and prix_vente:
            if prix_vente < prix_achat:
                raise ValidationError(
                    "Le prix de vente ne peut pas être inférieur au prix d'achat."
                )

            # Avertissement si la marge est faible
            marge_pourcentage = ((prix_vente - prix_achat) / prix_achat) * 100
            if marge_pourcentage < 10:
                self.add_error(
                    "prix_vente",
                    f"Attention: Marge faible ({marge_pourcentage:.1f}%). "
                    f"Vérifiez les prix.",
                )

        return cleaned_data


class ProduitSearchForm(forms.Form):
    """Formulaire de recherche et filtrage des produits"""

    nom = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Rechercher par nom..."}
        ),
        label="Nom",
    )

    code_produit = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Code produit..."}
        ),
        label="Code",
    )

    type_produit = forms.ChoiceField(
        choices=[("", "Tous les types")] + list(Produit.TypeProduit.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Type",
    )

    prix_min = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "Prix min",
            }
        ),
        label="Prix min (€)",
    )

    prix_max = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "Prix max",
            }
        ),
        label="Prix max (€)",
    )


class StockForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ["produit", "service", "quantite", "date_peremption", "numero_lot"]
        widgets = {
            "produit": forms.Select(attrs={"class": "form-select"}),
            "service": forms.Select(attrs={"class": "form-select"}),
            "quantite": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "date_peremption": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "numero_lot": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Optionnel"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produit"].queryset = Produit.objects.all().order_by("nom")
        self.fields["service"].queryset = Service.objects.all().order_by("name")

    def clean_date_peremption(self):
        date_peremption = self.cleaned_data.get("date_peremption")
        if date_peremption and date_peremption < timezone.now().date():
            raise forms.ValidationError(
                "La date de péremption ne peut pas être dans le passé"
            )
        return date_peremption


class AjustementStockForm(forms.ModelForm):
    class Meta:
        model = AjustementStock
        fields = ["stock", "quantite_avant", "quantite_apres", "motif", "commentaire"]
        widgets = {
            "stock": forms.Select(attrs={"class": "form-select"}),
            "quantite_avant": forms.NumberInput(
                attrs={"class": "form-control", "readonly": True}
            ),
            "quantite_apres": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
            "motif": forms.Select(attrs={"class": "form-select"}),
            "commentaire": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Détails de l'ajustement...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].queryset = Stock.objects.filter(
            quantite__gt=0
        ).select_related("produit", "service")


class FournisseurForm(forms.ModelForm):
    class Meta:
        model = Fournisseur
        fields = "__all__"
        exclude = ["solde"]
        widgets = {
            "email": forms.EmailInput(attrs={"required": True}),
            "telephone": forms.TextInput(attrs={"pattern": "[0-9]{10}"}),
            "adresse": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": "500",
                }
            ),
        }

    def clean_code_fournisseur(self):
        code = self.cleaned_data["code_fournisseur"]
        if Fournisseur.objects.filter(code_fournisseur=code).exists():
            raise forms.ValidationError("Ce code fournisseur existe déjà")
        return code
