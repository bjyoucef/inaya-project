# pharmacies/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from rh.models import Personnel

from .models import (Achat, BonCommande, Fournisseur, HistoriquePaiement,
                     LigneCommande, OrdrePaiement, Produit, Stock, Transfert)


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
            # "description": forms.Textarea(
            #     attrs={
            #         "class": "form-control",
            #         "rows": 4,
            #         "placeholder": "Description du produit (optionnel)",
            #     }
            # ),
            # "est_actif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
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

    # est_actif = forms.ChoiceField(
    #     choices=[
    #         ("", "Tous"),
    #         ("true", "Actifs seulement"),
    #         ("false", "Inactifs seulement"),
    #     ],
    #     required=False,
    #     widget=forms.Select(attrs={"class": "form-select"}),
    #     label="Statut",
    # )

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


class OrdrePaiementForm(forms.ModelForm):
    class Meta:
        model = OrdrePaiement
        fields = ["commande", "montant", "mode_paiement", "date_paiement", "preuve"]
        widgets = {
            "date_paiement": forms.DateInput(
                attrs={"type": "date", "class": "datepicker"}, format="%Y-%m-%d"
            ),
            "mode_paiement": forms.Select(attrs={"class": "select2"}),
            "commande": forms.Select(attrs={"class": "select2-commandes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["commande"].queryset = BonCommande.objects.filter(
            statut__in=["LIVRE", "FACTURE"]
        ).select_related("fournisseur")

        if self.instance and self.instance.pk:
            self.fields["commande"].disabled = True
            self.fields["montant"].disabled = True

    def clean_montant(self):
        commande = self.cleaned_data.get("commande")
        montant = self.cleaned_data.get("montant")

        if commande and montant:
            # Calcul du montant déjà payé
            total_paye = (
                commande.paiements.aggregate(total=Sum("montant"))["total"] or 0
            )

            # Calcul du montant restant
            montant_restant = commande.montant_total - total_paye

            # Si modification d'un paiement existant
            if self.instance and self.instance.pk:
                montant_restant += self.instance.montant

            if montant > montant_restant:
                raise ValidationError(
                    f"Montant excédentaire. Maximum autorisé : {montant_restant} {commande.devise}"
                )

            if montant > commande.fournisseur.credit_disponible:
                raise ValidationError(
                    f"Crédit insuffisant chez le fournisseur. Crédit disponible : "
                    f"{commande.fournisseur.credit_disponible} {commande.devise}"
                )

        return montant

    def clean_date_paiement(self):
        date_paiement = self.cleaned_data.get("date_paiement")
        if date_paiement > timezone.now().date():
            raise ValidationError("La date de paiement ne peut pas être dans le futur")
        return date_paiement

    def clean(self):
        cleaned_data = super().clean()
        commande = cleaned_data.get("commande")
        montant = cleaned_data.get("montant")

        if commande and montant:
            # Vérification du délai de paiement
            delai_max = commande.fournisseur.conditions_paiement
            delai_reel = (timezone.now().date() - commande.date_commande).days

            if delai_reel > delai_max:
                self.add_warning(
                    f"Délai de paiement dépassé de {delai_reel - delai_max} jours !"
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if not instance.reference:
            instance.reference = f"PAY-{timezone.now().strftime('%Y%m%d')}-{BonCommande.objects.count() + 1}"

        if commit:
            instance.save()
            self.save_m2m()

            # Mise à jour du statut de la commande si totalement payée
            total_paye = instance.commande.paiements.aggregate(total=Sum("montant"))[
                "total"
            ]

            if total_paye >= instance.commande.montant_total:
                instance.commande.statut = "FACTURE"
                instance.commande.save()

        return instance

    def add_warning(self, message):
        if "__all__" in self._errors:
            self._errors["__all__"].append(message)
        else:
            self._errors["__all__"] = self.error_class([message])


from django import forms
from django.forms import DateInput, inlineformset_factory

from .models import LigneCommande


class LigneCommandeForm(forms.ModelForm):
    class Meta:
        model = LigneCommande
        fields = [
            "produit",
            "quantite",
            "prix_unitaire",
            "date_peremption",
            "numero_lot",
        ]

        widgets = {
            'date_peremption': DateInput(attrs={'type': 'date'}),
        }

    def clean_quantite(self):
        quantite = self.cleaned_data.get("quantite")
        if quantite <= 0:
            raise forms.ValidationError("La quantité doit être supérieure à zéro")
        return quantite

LigneCommandeFormSet = inlineformset_factory(
    BonCommande,
    LigneCommande,
    form=LigneCommandeForm,  # Ajoutez ceci
    fields=("produit", "quantite", "prix_unitaire", "date_peremption", "numero_lot"),
    extra=1,
    can_delete=True,
)


# pharmacies/forms.py
from django import forms

from .models import BonLivraison


class BonLivraisonForm(forms.ModelForm):
    class Meta:
        model = BonLivraison
        fields = ["fichier_bl"]

    def __init__(self, *args, **kwargs):
        self.commande_pk = kwargs.pop("commande_pk", None)
        super().__init__(*args, **kwargs)
        if self.commande_pk:
            self.instance.commande_id = self.commande_pk
