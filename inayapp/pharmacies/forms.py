# pharmacies/forms.py
from django import forms

from rh.models import Personnel
from .models import Produit, Stock, Transfert, Achat, LigneCommande
from django import forms
from .models import Fournisseur, HistoriquePaiement
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from .models import OrdrePaiement, BonCommande, Fournisseur


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
from .models import LigneCommande
from django.forms import DateInput, inlineformset_factory

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
