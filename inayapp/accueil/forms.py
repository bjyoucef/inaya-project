# forms.py
from django import forms
from django.contrib.auth.models import User, Permission, Group
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError


class UserPermissionForm(forms.ModelForm):
    """Formulaire pour modifier les permissions d'un utilisateur"""

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Sélectionnez les permissions pour cet utilisateur",
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Sélectionnez les groupes pour cet utilisateur",
    )

    class Meta:
        model = User
        fields = ["is_staff", "is_superuser", "is_active", "permissions", "groups"]
        widgets = {
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_superuser": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Organiser les permissions par modèle
        if self.instance.pk:
            self.fields["permissions"].initial = self.instance.user_permissions.all()
            self.fields["groups"].initial = self.instance.groups.all()


class GroupPermissionForm(forms.ModelForm):
    """Formulaire pour modifier les permissions d'un groupe"""

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related("content_type").all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Sélectionnez les permissions pour ce groupe",
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["permissions"].initial = self.instance.permissions.all()


class UserSearchForm(forms.Form):
    """Formulaire de recherche d'utilisateurs"""

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Rechercher par nom, email ou nom d'utilisateur...",
            }
        ),
    )

    is_active = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    is_staff = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    is_superuser = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )


class BulkPermissionForm(forms.Form):
    """Formulaire pour modifier les permissions en lot"""

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Sélectionnez les utilisateurs à modifier",
    )

    action = forms.ChoiceField(
        choices=[
            ("add_permissions", "Ajouter des permissions"),
            ("remove_permissions", "Supprimer des permissions"),
            ("add_to_groups", "Ajouter aux groupes"),
            ("remove_from_groups", "Supprimer des groupes"),
            ("set_staff", "Définir comme staff"),
            ("unset_staff", "Retirer le statut staff"),
            ("activate", "Activer les comptes"),
            ("deactivate", "Désactiver les comptes"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Permissions à ajouter ou supprimer",
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Groupes à ajouter ou supprimer",
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        permissions = cleaned_data.get("permissions")
        groups = cleaned_data.get("groups")

        if action in ["add_permissions", "remove_permissions"] and not permissions:
            raise ValidationError("Vous devez sélectionner au moins une permission.")

        if action in ["add_to_groups", "remove_from_groups"] and not groups:
            raise ValidationError("Vous devez sélectionner au moins un groupe.")

        return cleaned_data


class PermissionFilterForm(forms.Form):
    """Formulaire pour filtrer les permissions"""

    app_label = forms.ChoiceField(
        choices=[], required=False, widget=forms.Select(attrs={"class": "form-control"})
    )

    content_type = forms.ChoiceField(
        choices=[], required=False, widget=forms.Select(attrs={"class": "form-control"})
    )

    action_type = forms.ChoiceField(
        choices=[
            ("", "Toutes les actions"),
            ("add", "Ajout"),
            ("change", "Modification"),
            ("delete", "Suppression"),
            ("view", "Lecture"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Choix pour app_label
        from django.contrib.contenttypes.models import ContentType

        app_labels = ContentType.objects.values_list("app_label", flat=True).distinct()
        self.fields["app_label"].choices = [("", "Toutes les applications")] + [
            (label, label.title()) for label in sorted(app_labels)
        ]

        # Choix pour content_type
        content_types = ContentType.objects.all()
        self.fields["content_type"].choices = [("", "Tous les modèles")] + [
            (ct.id, f"{ct.app_label} - {ct.model}") for ct in content_types
        ]


class CreateUserWithPermissionsForm(UserCreationForm):
    """Formulaire pour créer un utilisateur avec des permissions"""

    email = forms.EmailField(
        required=True, widget=forms.EmailInput(attrs={"class": "form-control"})
    )

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    is_staff = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Sélectionnez les groupes pour ce nouvel utilisateur",
    )

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Sélectionnez les permissions individuelles",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
            "is_staff",
            "groups",
            "permissions",
        )
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.is_staff = self.cleaned_data["is_staff"]

        if commit:
            user.save()
            # Assigner les groupes et permissions
            if self.cleaned_data["groups"]:
                user.groups.set(self.cleaned_data["groups"])
            if self.cleaned_data["permissions"]:
                user.user_permissions.set(self.cleaned_data["permissions"])

        return user


class GroupFilterForm(forms.Form):
    """Formulaire pour filtrer les groupes"""

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Rechercher par nom de groupe...",
            }
        ),
    )

    has_users = forms.BooleanField(
        required=False,
        label="Groupes avec utilisateurs",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    has_permissions = forms.BooleanField(
        required=False,
        label="Groupes avec permissions",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    min_permissions = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nombre minimum de permissions",
            }
        ),
    )


class PermissionExportForm(forms.Form):
    """Formulaire pour exporter les permissions"""

    EXPORT_FORMATS = [
        ("csv", "CSV"),
        ("json", "JSON"),
        ("xlsx", "Excel"),
    ]

    format = forms.ChoiceField(
        choices=EXPORT_FORMATS, widget=forms.Select(attrs={"class": "form-control"})
    )

    include_users = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    include_groups = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    include_permissions = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )


class PermissionTemplateForm(forms.Form):
    """Formulaire pour appliquer des templates de permissions"""

    ROLE_TEMPLATES = [
        ("admin", "Administrateur"),
        ("editor", "Éditeur"),
        ("viewer", "Lecteur"),
        ("moderator", "Modérateur"),
        ("custom", "Personnalisé"),
    ]

    template = forms.ChoiceField(
        choices=ROLE_TEMPLATES, widget=forms.Select(attrs={"class": "form-control"})
    )

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Utilisateurs auxquels appliquer ce template",
    )

    replace_existing = forms.BooleanField(
        required=False,
        initial=False,
        label="Remplacer les permissions existantes",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Si coché, supprime les permissions actuelles avant d'appliquer le template",
    )


class AdvancedUserSearchForm(forms.Form):
    """Formulaire de recherche avancée d'utilisateurs"""

    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    email = forms.EmailField(
        required=False, widget=forms.EmailInput(attrs={"class": "form-control"})
    )

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    is_active = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "Tous"), (True, "Actif"), (False, "Inactif")],
            attrs={"class": "form-control"},
        ),
    )

    is_staff = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "Tous"), (True, "Staff"), (False, "Non-staff")],
            attrs={"class": "form-control"},
        ),
    )

    is_superuser = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "Tous"), (True, "Superuser"), (False, "Non-superuser")],
            attrs={"class": "form-control"},
        ),
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )

    has_permissions = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    date_joined_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    date_joined_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    last_login_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    last_login_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )


class PermissionComparisonForm(forms.Form):
    """Formulaire pour comparer les permissions entre utilisateurs ou groupes"""

    COMPARISON_TYPES = [
        ("users", "Comparer des utilisateurs"),
        ("groups", "Comparer des groupes"),
        ("user_group", "Comparer utilisateur et groupe"),
    ]

    comparison_type = forms.ChoiceField(
        choices=COMPARISON_TYPES, widget=forms.Select(attrs={"class": "form-control"})
    )

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control"}),
    )

    show_common = forms.BooleanField(
        required=False,
        initial=True,
        label="Afficher les permissions communes",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    show_unique = forms.BooleanField(
        required=False,
        initial=True,
        label="Afficher les permissions uniques",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        comparison_type = cleaned_data.get("comparison_type")
        users = cleaned_data.get("users")
        groups = cleaned_data.get("groups")

        if comparison_type == "users" and not users:
            raise ValidationError("Vous devez sélectionner au moins deux utilisateurs.")
        elif comparison_type == "groups" and not groups:
            raise ValidationError("Vous devez sélectionner au moins deux groupes.")
        elif comparison_type == "user_group" and (not users or not groups):
            raise ValidationError(
                "Vous devez sélectionner au moins un utilisateur et un groupe."
            )

        return cleaned_data
