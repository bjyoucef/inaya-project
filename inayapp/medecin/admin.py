from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Medecin


@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    # Configuration pour l'autocomplétion (requis par les autres admins)
    search_fields = ["first_name", "last_name", "email", "specialite"]

    # Liste des champs affichés
    list_display = [
        "nom_complet_display",
        "specialite_display",
        "email",
        "telephone",
        "services_display",
        "created_at",
        "created_by",
    ]

    # Filtres latéraux
    list_filter = ["specialite", "services", "created_at", "created_by"]

    # Champs de recherche
    search_fields = ["first_name", "last_name", "email", "specialite", "telephone"]

    # Champs en lecture seule
    readonly_fields = ["created_at", "solde_consommations_display", "nom_complet"]

    # Organisation des champs dans le formulaire
    fieldsets = (
        (
            "Informations personnelles",
            {"fields": ("first_name", "last_name", "email", "telephone")},
        ),
        ("Informations professionnelles", {"fields": ("specialite", "services")}),
        (
            "Informations système",
            {"fields": ("created_by", "created_at"), "classes": ("collapse",)},
        ),
        (
            "Statistiques",
            {
                "fields": ("nom_complet", "solde_consommations_display"),
                "classes": ("collapse",),
            },
        ),
    )

    # Champs à utiliser pour l'autocomplétion
    autocomplete_fields = ["services"]

    # Filtres horizontaux pour les relations ManyToMany
    filter_horizontal = ["services"]

    # Nombre d'éléments par page
    list_per_page = 25

    # Tri par défaut
    ordering = ["-created_at"]


    def get_queryset(self, request):
        """Optimise les requêtes avec prefetch_related"""
        return (
            super()
            .get_queryset(request)
            .prefetch_related("services")
            .select_related("created_by")
        )

    def save_model(self, request, obj, form, change):
        """Automatiquement définir created_by lors de la création"""
        if not change:  # Si c'est une création
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # Méthodes d'affichage personnalisées
    def nom_complet_display(self, obj):
        """Affiche le nom complet avec un lien vers la page de détail"""
        url = reverse("admin:medecin_medecin_change", args=[obj.pk])
        return format_html(
            '<a href="{}" title="Voir les détails"><strong>Dr. {}</strong></a>',
            url,
            obj.nom_complet or "Nom incomplet",
        )

    nom_complet_display.short_description = "Nom complet"
    nom_complet_display.admin_order_field = "last_name"

    def specialite_display(self, obj):
        """Affiche la spécialité avec une icône"""
        if obj.specialite:
            return format_html(
                '<span title="Spécialité médicale"><i class="fas fa-stethoscope"></i> {}</span>',
                obj.specialite,
            )
        return format_html('<span class="text-muted">Non spécifiée</span>')

    specialite_display.short_description = "Spécialité"
    specialite_display.admin_order_field = "specialite"

    def services_display(self, obj):
        """Affiche les services associés"""
        services = obj.services.all()
        if services:
            services_list = []
            for service in services:  # Limite à 3 pour l'affichage
                services_list.append(
                    '<span style="background: #007bff; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin: 1px;">{}</span>'.format(
                        service.name
                    )
                )

            return mark_safe(" ".join(services_list))
        return format_html('<span class="text-muted">Aucun service</span>')

    services_display.short_description = "Services"


    def solde_consommations_display(self, obj):
        """Version détaillée du solde pour la page de détail"""
        solde = obj.solde_consommations
        if solde > 0:
            return format_html(
                '<span style="color: green; font-weight: bold; font-size: 1.2em;">{:.2f} DA</span><br>'
                '<small class="text-muted">Solde positif</small>',
                solde,
            )
        elif solde < 0:
            return format_html(
                '<span style="color: red; font-weight: bold; font-size: 1.2em;">{:.2f} DA</span><br>'
                '<small class="text-muted">Solde négatif</small>',
                solde,
            )
        else:
            return format_html(
                '<span class="text-muted; font-size: 1.2em;">0.00 DA</span><br>'
                '<small class="text-muted">Aucune consommation</small>'
            )

    solde_consommations_display.short_description = "Solde des consommations"


    # Personnalisation de l'affichage
    def has_add_permission(self, request):
        """Contrôle qui peut ajouter des médecins"""
        return request.user.has_perm("medecin.add_medecin")

    def has_change_permission(self, request, obj=None):
        """Contrôle qui peut modifier des médecins"""
        return request.user.has_perm("medecin.change_medecin")

    def has_delete_permission(self, request, obj=None):
        """Contrôle qui peut supprimer des médecins"""
        return request.user.has_perm("medecin.delete_medecin")

    class Media:
        """Ajoute des CSS/JS personnalisés si nécessaire"""

        css = {"all": ("admin/css/medecin_admin.css",)}  # Optionnel
        js = ("admin/js/medecin_admin.js",)  # Optionnel
