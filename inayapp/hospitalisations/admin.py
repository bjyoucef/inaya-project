from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.contrib.admin import SimpleListFilter
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from .models import Room, Bed


class ServiceHospitalierFilter(SimpleListFilter):
    """Filtre pour les services d'hospitalisation uniquement"""

    title = "Service d'hospitalisation"
    parameter_name = "service_hospitalier"

    def lookups(self, request, model_admin):
        from medical.models import Service

        services = Service.objects.filter(est_hospitalier=True)
        return [(service.id, service.name) for service in services]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(service_id=self.value())
        return queryset.filter(service__est_hospitalier=True)


class BedConfigurationInline(admin.TabularInline):
    """Configuration inline des lits pour les chambres"""

    model = Bed
    extra = 0
    fields = (
        "bed_number",
        "is_active",
        "bed_type",
        "equipment_notes",
        "maintenance_required",
    )
    verbose_name = "Configuration des lits"
    verbose_name_plural = "Configuration des lits"

    def get_queryset(self, request):
        """Affiche tous les lits, même inactifs, pour la configuration"""
        return super().get_queryset(request)


@admin.register(Room)
class RoomConfigurationAdmin(admin.ModelAdmin):
    """Administration pour la configuration des chambres d'hospitalisation"""

    list_display = (
        "room_number",
        "service_name",
        "floor",
        "room_type_display",
        "bed_capacity",
        "configured_beds_count",
        "configuration_status",
        "occupancy_display",
        "monthly_revenue_display",
        "is_active",
    )

    list_filter = (
        ServiceHospitalierFilter,
        "floor",
        "room_type",
        "is_active",
        "bed_capacity",
        "maintenance_required",
    )

    search_fields = ("room_number", "service__name")
    ordering = ("service__name", "floor", "room_number")
    list_per_page = 30
    inlines = [BedConfigurationInline]

    fieldsets = (
        (
            "Informations de base",
            {
                "fields": ("room_number", "service", "floor"),
                "description": "Informations principales de la chambre",
            },
        ),
        (
            "Configuration",
            {
                "fields": ("room_type", "bed_capacity", "room_equipment"),
                "description": "Configuration technique de la chambre",
            },
        ),
        (
            "Tarification",
            {
                "fields": ("night_price",),
                "description": "Configuration des prix",
            },
        ),
        (
            "Paramètres",
            {
                "fields": ("is_active", "maintenance_required", "special_requirements"),
                "description": "Paramètres d'activation et exigences spéciales",
            },
        ),
        (
            "Outils de configuration",
            {
                "fields": ("auto_configure_beds",),
                "classes": ("collapse",),
                "description": "Outils pour configurer automatiquement les lits",
            },
        ),
    )

    readonly_fields = ("auto_configure_beds",)

    def get_queryset(self, request):
        """Limite aux services d'hospitalisation et optimise les requêtes"""
        queryset = super().get_queryset(request)
        return (
            queryset.filter(service__est_hospitalier=True)
            .select_related("service")
            .prefetch_related("beds", "beds__admissions")
        )

    def service_name(self, obj):
        """Affichage du nom du service"""
        return obj.service.name

    service_name.short_description = "Service d'hospitalisation"
    service_name.admin_order_field = "service__name"

    def room_type_display(self, obj):
        """Affichage coloré du type de chambre"""
        type_colors = {
            "single": "#3498db",
            "double": "#2ecc71",
            "triple": "#f39c12",
            "quad": "#e74c3c",
            "vip": "#9b59b6",
            "soins_intensifs": "#e67e22",
            "pediatrie": "#1abc9c",
        }
        color = type_colors.get(obj.room_type, "#95a5a6")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_room_type_display(),
        )

    room_type_display.short_description = "Type de chambre"

    def configured_beds_count(self, obj):
        """Nombre de lits configurés"""
        count = obj.beds.count()
        capacity = obj.bed_capacity

        if count == capacity:
            color = "#27ae60"  # Vert
            icon = "✓"
        elif count < capacity:
            color = "#f39c12"  # Orange
            icon = "⚠"
        else:
            color = "#e74c3c"  # Rouge
            icon = "⚠"

        return format_html(
            '<span style="color: {};">{} {} / {}</span>', color, icon, count, capacity
        )

    configured_beds_count.short_description = "Lits configurés"

    def configuration_status(self, obj):
        """Statut de configuration"""
        beds_count = obj.beds.count()
        capacity = obj.bed_capacity
        active_beds = obj.beds.filter(is_active=True).count()

        if beds_count == 0:
            return format_html('<span style="color: #e74c3c;">🔴 Non configurée</span>')
        elif beds_count < capacity:
            return format_html(
                '<span style="color: #f39c12;">🟡 Configuration incomplète</span>'
            )
        elif active_beds == 0:
            return format_html(
                '<span style="color: #95a5a6;">⚪ Configurée mais inactive</span>'
            )
        else:
            return format_html(
                '<span style="color: #27ae60;">🟢 Configurée et active</span>'
            )

    configuration_status.short_description = "Statut de configuration"

    def occupancy_display(self, obj):
        """Affichage du taux d'occupation"""
        try:
            rate = obj.occupancy_rate
            occupied = obj.occupied_beds_count
            total = obj.bed_capacity

            if rate == 0:
                color = "#95a5a6"  # Gris
                icon = "⚪"
            elif rate < 50:
                color = "#27ae60"  # Vert
                icon = "🟢"
            elif rate < 80:
                color = "#f39c12"  # Orange
                icon = "🟡"
            else:
                color = "#e74c3c"  # Rouge
                icon = "🔴"

            return format_html(
                '<span style="color: {};">{} {}% ({}/{})</span>',
                color,
                icon,
                rate,
                occupied,
                total,
            )
        except Exception:
            return format_html('<span style="color: #95a5a6;">-</span>')

    occupancy_display.short_description = "Occupation"

    def monthly_revenue_display(self, obj):
        """Affichage des revenus mensuels"""
        try:
            revenue = obj.monthly_revenue
            if revenue > 0:
                return format_html(
                    '<span style="color: #27ae60; font-weight: bold;">{} DA</span>',
                    revenue,
                )
            return format_html('<span style="color: #95a5a6;">0 DA</span>')
        except Exception:
            return format_html('<span style="color: #95a5a6;">-</span>')

    monthly_revenue_display.short_description = "Revenus du mois"

    def auto_configure_beds(self, obj):
        """Outil pour configurer automatiquement les lits"""
        if obj.pk:  # Seulement si l'objet existe
            return format_html(
                """
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
                    <h4>Configuration automatique des lits</h4>
                    <p>Capacité configurée: <strong>{} lits</strong></p>
                    <p>Lits actuels: <strong>{} lits</strong></p>
                    <p>Lits actifs: <strong>{} lits</strong></p>
                    <br>
                    <button type="button" onclick="configureBedsAutomatically({})" 
                            class="button" style="background: #007cba; color: white;">
                        🔧 Configurer automatiquement les lits
                    </button>
                    <button type="button" onclick="resetBedConfiguration({})" 
                            class="button" style="background: #dc3545; color: white; margin-left: 10px;">
                        🗑️ Réinitialiser la configuration
                    </button>
                    <button type="button" onclick="activateAllBeds({})" 
                            class="button" style="background: #28a745; color: white; margin-left: 10px;">
                        ✅ Activer tous les lits
                    </button>
                </div>
                <script>
                function configureBedsAutomatically(roomId) {{
                    if(confirm('Voulez-vous configurer automatiquement les lits pour cette chambre?')) {{
                        window.location.href = '/admin/hospitalization/room/' + roomId + '/configure-beds/';
                    }}
                }}
                function resetBedConfiguration(roomId) {{
                    if(confirm('Attention! Cela supprimera tous les lits configurés. Continuer?')) {{
                        window.location.href = '/admin/hospitalization/room/' + roomId + '/reset-beds/';
                    }}
                }}
                function activateAllBeds(roomId) {{
                    if(confirm('Activer tous les lits de cette chambre?')) {{
                        window.location.href = '/admin/hospitalization/room/' + roomId + '/activate-beds/';
                    }}
                }}
                </script>
                """,
                obj.bed_capacity,
                obj.beds.count(),
                obj.beds.filter(is_active=True).count(),
                obj.id,
                obj.id,
                obj.id,
            )
        return (
            "Sauvegardez d'abord la chambre pour accéder aux outils de configuration."
        )

    auto_configure_beds.short_description = "Configuration automatique"

    def get_urls(self):
        """Ajoute des URLs personnalisées pour les actions de configuration"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:room_id>/configure-beds/",
                self.admin_site.admin_view(self.configure_beds_view),
                name="configure_beds",
            ),
            path(
                "<int:room_id>/reset-beds/",
                self.admin_site.admin_view(self.reset_beds_view),
                name="reset_beds",
            ),
            path(
                "<int:room_id>/activate-beds/",
                self.admin_site.admin_view(self.activate_beds_view),
                name="activate_beds",
            ),
        ]
        return custom_urls + urls

    def configure_beds_view(self, request, room_id):
        """Vue pour configurer automatiquement les lits"""
        try:
            room = Room.objects.get(pk=room_id)

            existing_beds = room.beds.count()
            beds_needed = room.bed_capacity - existing_beds

            if beds_needed > 0:
                # Types de lits selon le type de chambre
                bed_types = {
                    "single": "standard",
                    "double": "standard",
                    "triple": "standard",
                    "quad": "standard",
                    "vip": "electrique",
                    "soins_intensifs": "reanimation",
                    "pediatrie": "pediatrique",
                }

                bed_type = bed_types.get(room.room_type, "standard")

                for i in range(existing_beds + 1, room.bed_capacity + 1):
                    Bed.objects.create(
                        room=room,
                        bed_number=f"L{i:02d}",
                        bed_type=bed_type,
                        is_active=True,
                    )

                messages.success(
                    request,
                    f"{beds_needed} lit(s) configuré(s) automatiquement pour la chambre {room.room_number}.",
                )
            else:
                messages.info(request, "La chambre est déjà entièrement configurée.")

        except Room.DoesNotExist:
            messages.error(request, "Chambre introuvable.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la configuration: {str(e)}")

        return redirect("admin:hospitalization_room_change", room_id)

    def reset_beds_view(self, request, room_id):
        """Vue pour réinitialiser la configuration des lits"""
        try:
            room = Room.objects.get(pk=room_id)

            # Vérifier qu'aucun lit n'est occupé
            occupied_beds = room.beds.filter(is_occupied=True).count()
            if occupied_beds > 0:
                messages.error(
                    request,
                    f"Impossible de réinitialiser: {occupied_beds} lit(s) sont actuellement occupé(s).",
                )
                return redirect("admin:hospitalization_room_change", room_id)

            # Supprimer tous les lits
            deleted_count = room.beds.count()
            room.beds.all().delete()

            messages.success(
                request,
                f"{deleted_count} lit(s) supprimé(s) de la chambre {room.room_number}.",
            )

        except Room.DoesNotExist:
            messages.error(request, "Chambre introuvable.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la réinitialisation: {str(e)}")

        return redirect("admin:hospitalization_room_change", room_id)

    def activate_beds_view(self, request, room_id):
        """Vue pour activer tous les lits d'une chambre"""
        try:
            room = Room.objects.get(pk=room_id)
            updated_count = room.beds.update(is_active=True)

            messages.success(
                request,
                f"{updated_count} lit(s) activé(s) dans la chambre {room.room_number}.",
            )

        except Room.DoesNotExist:
            messages.error(request, "Chambre introuvable.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'activation: {str(e)}")

        return redirect("admin:hospitalization_room_change", room_id)

    actions = [
        "configure_beds_for_selected_rooms",
        "activate_selected_rooms",
        "deactivate_selected_rooms",
        "mark_for_maintenance",
        "clear_maintenance_flag",
        "duplicate_room_configuration",
    ]

    def configure_beds_for_selected_rooms(self, request, queryset):
        """Configure automatiquement les lits pour les chambres sélectionnées"""
        configured_count = 0
        beds_created = 0

        for room in queryset:
            existing_beds = room.beds.count()
            beds_needed = room.bed_capacity - existing_beds

            if beds_needed > 0:
                # Types de lits selon le type de chambre
                bed_types = {
                    "single": "standard",
                    "double": "standard",
                    "triple": "standard",
                    "quad": "standard",
                    "vip": "electrique",
                    "soins_intensifs": "reanimation",
                    "pediatrie": "pediatrique",
                }

                bed_type = bed_types.get(room.room_type, "standard")

                for i in range(existing_beds + 1, room.bed_capacity + 1):
                    Bed.objects.create(
                        room=room,
                        bed_number=f"L{i:02d}",
                        bed_type=bed_type,
                        is_active=True,
                    )
                    beds_created += 1
                configured_count += 1

        self.message_user(
            request,
            f"{configured_count} chambre(s) configurée(s) avec {beds_created} nouveau(x) lit(s).",
        )

    configure_beds_for_selected_rooms.short_description = (
        "🔧 Configurer les lits automatiquement"
    )

    def activate_selected_rooms(self, request, queryset):
        """Active les chambres sélectionnées"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} chambre(s) activée(s).")

    activate_selected_rooms.short_description = "✅ Activer les chambres"

    def deactivate_selected_rooms(self, request, queryset):
        """Désactive les chambres sélectionnées"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} chambre(s) désactivée(s).")

    deactivate_selected_rooms.short_description = "❌ Désactiver les chambres"

    def mark_for_maintenance(self, request, queryset):
        """Marque les chambres pour maintenance"""
        count = queryset.update(maintenance_required=True)
        self.message_user(request, f"{count} chambre(s) marquée(s) pour maintenance.")

    mark_for_maintenance.short_description = "🔧 Marquer pour maintenance"

    def clear_maintenance_flag(self, request, queryset):
        """Retire le marquage de maintenance"""
        count = queryset.update(maintenance_required=False)
        self.message_user(
            request, f"Marquage maintenance retiré pour {count} chambre(s)."
        )

    clear_maintenance_flag.short_description = "✅ Retirer marquage maintenance"

    def duplicate_room_configuration(self, request, queryset):
        """Duplique la configuration d'une chambre vers d'autres"""
        if queryset.count() > 1:
            self.message_user(
                request,
                "Veuillez sélectionner une seule chambre modèle pour la duplication.",
                level=messages.WARNING,
            )
        else:
            self.message_user(
                request,
                "Fonctionnalité de duplication à implémenter avec une vue personnalisée.",
                level=messages.INFO,
            )

    duplicate_room_configuration.short_description = "📋 Dupliquer la configuration"


class BedTypeFilter(SimpleListFilter):
    """Filtre par type de lit"""

    title = "Type de lit"
    parameter_name = "bed_type"

    def lookups(self, request, model_admin):
        return [
            ("standard", "Lit Standard"),
            ("electrique", "Lit Électrique"),
            ("isolation", "Lit d'Isolation"),
            ("pediatrique", "Lit Pédiatrique"),
            ("geriatrique", "Lit Gériatrique"),
            ("reanimation", "Lit de Réanimation"),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(bed_type=self.value())
        return queryset


class BedStatusFilter(SimpleListFilter):
    """Filtre par statut du lit"""

    title = "Statut du lit"
    parameter_name = "bed_status"

    def lookups(self, request, model_admin):
        return [
            ("available", "Disponible"),
            ("occupied", "Occupé"),
            ("maintenance", "En maintenance"),
            ("inactive", "Inactif"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "available":
            return queryset.filter(
                is_active=True, is_occupied=False, maintenance_required=False
            )
        elif self.value() == "occupied":
            return queryset.filter(is_occupied=True)
        elif self.value() == "maintenance":
            return queryset.filter(maintenance_required=True)
        elif self.value() == "inactive":
            return queryset.filter(is_active=False)
        return queryset


@admin.register(Bed)
class BedConfigurationAdmin(admin.ModelAdmin):
    """Administration pour la configuration des lits"""

    list_display = (
        "bed_display",
        "room_info",
        "service_info",
        "bed_type_display",
        "equipment_status",
        "patient_info",
        "configuration_status",
        "last_cleaned_display",
        "is_active",
    )

    list_filter = (
        "room__service",
        "room__floor",
        BedTypeFilter,
        BedStatusFilter,
        "is_active",
        "room__room_type",
        "maintenance_required",
    )

    search_fields = ("bed_number", "room__room_number", "room__service__name")

    ordering = ("room__service__name", "room__room_number", "bed_number")
    list_per_page = 50

    fieldsets = (
        (
            "Identification",
            {
                "fields": ("room", "bed_number"),
                "description": "Informations d'identification du lit",
            },
        ),
        (
            "Configuration technique",
            {
                "fields": ("bed_type", "bed_equipment", "equipment_notes"),
                "description": "Configuration et équipements du lit",
            },
        ),
        (
            "Paramètres de fonctionnement",
            {
                "fields": ("is_active", "maintenance_required", "special_requirements"),
                "description": "Paramètres d'utilisation et maintenance",
            },
        ),
        (
            "Informations d'occupation",
            {
                "fields": ("is_occupied", "last_cleaned"),
                "description": "État d'occupation et nettoyage",
            },
        ),
        (
            "Horodatage",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
                "description": "Informations de création et modification",
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        """Optimise les requêtes et limite aux services d'hospitalisation"""
        queryset = super().get_queryset(request)
        return (
            queryset.filter(room__service__est_hospitalier=True)
            .select_related("room", "room__service")
            .prefetch_related("admissions", "admissions__patient")
        )

    def bed_display(self, obj):
        """Affichage formaté du lit"""
        return format_html(
            "<strong>Lit {}</strong><br><small>Ch. {}</small>",
            obj.bed_number,
            obj.room.room_number,
        )

    bed_display.short_description = "Lit"
    bed_display.admin_order_field = "bed_number"

    def room_info(self, obj):
        """Information de la chambre"""
        return format_html(
            '<a href="{}" title="Voir la chambre">Chambre {}</a><br><small>Étage {}</small>',
            reverse("admin:hospitalization_room_change", args=[obj.room.id]),
            obj.room.room_number,
            obj.room.floor,
        )

    room_info.short_description = "Chambre"
    room_info.admin_order_field = "room__room_number"

    def service_info(self, obj):
        """Information du service"""
        return obj.room.service.name

    service_info.short_description = "Service"
    service_info.admin_order_field = "room__service__name"

    def bed_type_display(self, obj):
        """Affichage coloré du type de lit"""
        type_colors = {
            "standard": "#3498db",
            "electrique": "#f39c12",
            "isolation": "#e74c3c",
            "pediatrique": "#9b59b6",
            "geriatrique": "#1abc9c",
            "reanimation": "#e67e22",
        }
        color = type_colors.get(obj.bed_type, "#95a5a6")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_bed_type_display(),
        )

    bed_type_display.short_description = "Type de lit"

    def equipment_status(self, obj):
        """Statut des équipements"""
        if obj.maintenance_required:
            return format_html(
                '<span style="color: #e74c3c;">🔧 Maintenance requise</span>'
            )
        elif obj.bed_equipment:
            return format_html('<span style="color: #27ae60;">✅ Équipé</span>')
        else:
            return format_html('<span style="color: #95a5a6;">⚪ Standard</span>')

    equipment_status.short_description = "Équipements"

    def patient_info(self, obj):
        """Information du patient actuel"""
        try:
            current_patient = obj.current_patient
            if current_patient:
                return format_html(
                    '<span style="color: #e74c3c; font-weight: bold;">👤 {}</span>',
                    current_patient.nom_complet,
                )
            else:
                return format_html('<span style="color: #27ae60;">🟢 Libre</span>')
        except Exception:
            return format_html('<span style="color: #95a5a6;">-</span>')

    patient_info.short_description = "Patient"

    def configuration_status(self, obj):
        """Statut de configuration"""
        if not obj.is_active:
            return format_html('<span style="color: #95a5a6;">⚪ Inactif</span>')
        elif obj.maintenance_required:
            return format_html('<span style="color: #f39c12;">🔧 En maintenance</span>')
        elif obj.is_occupied:
            return format_html('<span style="color: #e74c3c;">🔴 Occupé</span>')
        else:
            return format_html('<span style="color: #27ae60;">✅ Disponible</span>')

    configuration_status.short_description = "Statut"

    def last_cleaned_display(self, obj):
        """Affichage de la dernière désinfection"""
        if obj.last_cleaned:
            return format_html(
                '<span style="color: #27ae60;">{}</span>',
                obj.last_cleaned.strftime("%d/%m/%Y %H:%M"),
            )
        return format_html('<span style="color: #f39c12;">⚠ Jamais nettoyé</span>')

    last_cleaned_display.short_description = "Dernière désinfection"

    actions = [
        "activate_selected_beds",
        "deactivate_selected_beds",
        "mark_for_maintenance",
        "clear_maintenance_flag",
        "mark_as_cleaned",
        "standardize_bed_numbering",
    ]

    def activate_selected_beds(self, request, queryset):
        """Active les lits sélectionnés"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} lit(s) activé(s).")

    activate_selected_beds.short_description = "✅ Activer les lits"

    def deactivate_selected_beds(self, request, queryset):
        """Désactive les lits sélectionnés"""
        # Vérifier qu'aucun lit n'est occupé
        occupied_count = queryset.filter(is_occupied=True).count()
        if occupied_count > 0:
            self.message_user(
                request,
                f"Impossible de désactiver {occupied_count} lit(s) car ils sont occupés.",
                level=messages.ERROR,
            )
            return

        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} lit(s) désactivé(s).")

    deactivate_selected_beds.short_description = "❌ Désactiver les lits"

    def mark_for_maintenance(self, request, queryset):
        """Marque les lits pour maintenance"""
        count = queryset.update(maintenance_required=True)
        self.message_user(request, f"{count} lit(s) marqué(s) pour maintenance.")

    mark_for_maintenance.short_description = "🔧 Marquer pour maintenance"

    def clear_maintenance_flag(self, request, queryset):
        """Retire le marquage de maintenance"""
        count = queryset.update(maintenance_required=False)
        self.message_user(request, f"Marquage maintenance retiré pour {count} lit(s).")

    clear_maintenance_flag.short_description = "✅ Retirer marquage maintenance"

    def mark_as_cleaned(self, request, queryset):
        """Marque les lits comme nettoyés"""
        count = queryset.update(last_cleaned=timezone.now())
        self.message_user(request, f"{count} lit(s) marqué(s) comme nettoyé(s).")

    mark_as_cleaned.short_description = "🧹 Marquer comme nettoyé"

    def standardize_bed_numbering(self, request, queryset):
        """Standardise la numérotation des lits"""
        updated_count = 0
        for bed in queryset:
            # Logique de standardisation
            original_number = bed.bed_number
            if not bed.bed_number.startswith("L"):
                # Extraire le numéro et le formatter
                number_part = "".join(filter(str.isdigit, bed.bed_number))
                if number_part:
                    bed.bed_number = f"L{number_part.zfill(2)}"
                    bed.save()
                    updated_count += 1

        self.message_user(
            request, f"Numérotation standardisée pour {updated_count} lit(s)."
        )

    standardize_bed_numbering.short_description = "📝 Standardiser la numérotation"


# Vues personnalisées pour les actions en masse
class BedManagementView:
    """Classe utilitaire pour la gestion des lits"""

    @staticmethod
    def auto_configure_room_beds(room, bed_type=None):
        """Configure automatiquement les lits d'une chambre"""
        existing_beds = room.beds.count()
        beds_needed = room.bed_capacity - existing_beds

        if beds_needed <= 0:
            return 0

        if not bed_type:
            # Types de lits selon le type de chambre
            bed_types = {
                "single": "standard",
                "double": "standard",
                "triple": "standard",
                "quad": "standard",
                "vip": "electrique",
                "soins_intensifs": "reanimation",
                "pediatrie": "pediatrique",
            }
            bed_type = bed_types.get(room.room_type, "standard")

        beds_created = 0
        for i in range(existing_beds + 1, room.bed_capacity + 1):
            Bed.objects.create(
                room=room,
                bed_number=f"L{i:02d}",
                bed_type=bed_type,
                is_active=True,
                last_cleaned=timezone.now(),
            )
            beds_created += 1

        return beds_created

    @staticmethod
    def validate_room_configuration(room):
        """Valide la configuration d'une chambre"""
        errors = []
        warnings = []

        # Vérifications de base
        if room.bed_capacity <= 0:
            errors.append("La capacité de la chambre doit être supérieure à 0")

        if not room.service or not room.service.est_hospitalier:
            errors.append(
                "La chambre doit être associée à un service d'hospitalisation"
            )

        # Vérifications des lits
        beds_count = room.beds.count()
        if beds_count < room.bed_capacity:
            warnings.append(
                f"Configuration incomplète: {beds_count}/{room.bed_capacity} lits configurés"
            )

        active_beds = room.beds.filter(is_active=True).count()
        if active_beds == 0 and beds_count > 0:
            warnings.append("Aucun lit n'est actif dans cette chambre")

        maintenance_beds = room.beds.filter(maintenance_required=True).count()
        if maintenance_beds > 0:
            warnings.append(f"{maintenance_beds} lit(s) nécessitent une maintenance")

        return errors, warnings


# Administration personnalisée pour les rapports
class HospitalizationReportAdmin:
    """Administration pour les rapports d'hospitalisation"""

    def room_occupancy_report(self, request):
        """Rapport d'occupation des chambres"""
        from django.db.models import Count, Q, Avg

        rooms = (
            Room.objects.filter(service__est_hospitalier=True)
            .annotate(
                total_beds=Count("beds"),
                occupied_beds=Count("beds", filter=Q(beds__is_occupied=True)),
                active_beds=Count("beds", filter=Q(beds__is_active=True)),
                maintenance_beds=Count(
                    "beds", filter=Q(beds__maintenance_required=True)
                ),
            )
            .select_related("service")
        )

        context = {
            "rooms": rooms,
            "title": "Rapport d'occupation des chambres",
            "total_rooms": rooms.count(),
            "total_beds": sum(room.bed_capacity for room in rooms),
            "occupied_beds": sum(room.occupied_beds for room in rooms),
        }

        return render(
            request, "admin/hospitalization/room_occupancy_report.html", context
        )

    def bed_maintenance_report(self, request):
        """Rapport de maintenance des lits"""
        maintenance_beds = Bed.objects.filter(
            maintenance_required=True, room__service__est_hospitalier=True
        ).select_related("room", "room__service")

        context = {
            "maintenance_beds": maintenance_beds,
            "title": "Rapport de maintenance des lits",
            "total_maintenance": maintenance_beds.count(),
        }

        return render(
            request, "admin/hospitalization/bed_maintenance_report.html", context
        )


# Filtres avancés supplémentaires
class OccupancyRateFilter(SimpleListFilter):
    """Filtre par taux d'occupation"""

    title = "Taux d'occupation"
    parameter_name = "occupancy_rate"

    def lookups(self, request, model_admin):
        return [
            ("empty", "Vide (0%)"),
            ("low", "Faible (1-25%)"),
            ("medium", "Moyen (26-75%)"),
            ("high", "Élevé (76-99%)"),
            ("full", "Complet (100%)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "empty":
            return queryset.filter(beds__is_occupied=False).distinct()
        elif self.value() == "full":
            # Logique complexe pour les chambres pleines
            return queryset.annotate(
                occupied_count=Count("beds", filter=Q(beds__is_occupied=True))
            ).filter(occupied_count__gte=models.F("bed_capacity"))
        # Autres filtres nécessiteraient des calculs plus complexes
        return queryset


class FloorFilter(SimpleListFilter):
    """Filtre par étage"""

    title = "Étage"
    parameter_name = "floor"

    def lookups(self, request, model_admin):
        floors = (
            Room.objects.filter(service__est_hospitalier=True)
            .values_list("floor", flat=True)
            .distinct()
            .order_by("floor")
        )
        return [(floor, f"Étage {floor}") for floor in floors if floor]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(floor=self.value())
        return queryset


# Widgets personnalisés pour l'interface admin
class BedConfigurationWidget:
    """Widget personnalisé pour la configuration des lits"""

    @staticmethod
    def render_bed_grid(room):
        """Rendu en grille des lits d'une chambre"""
        beds = room.beds.all().order_by("bed_number")
        html = '<div class="bed-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0;">'

        for bed in beds:
            status_class = "occupied" if bed.is_occupied else "available"
            if bed.maintenance_required:
                status_class = "maintenance"
            elif not bed.is_active:
                status_class = "inactive"

            html += f"""
            <div class="bed-item {status_class}" style="
                border: 2px solid {'#e74c3c' if bed.is_occupied else '#27ae60'};
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                background: {'#ffeaea' if bed.is_occupied else '#eafaf1'};
            ">
                <strong>{bed.bed_number}</strong><br>
                <small>{bed.get_bed_type_display()}</small><br>
                <span style="color: {'#e74c3c' if bed.is_occupied else '#27ae60'};">
                    {bed.status_display}
                </span>
            </div>
            """

        # Ajouter des emplacements vides si nécessaire
        for i in range(len(beds), room.bed_capacity):
            html += f"""
            <div class="bed-item empty" style="
                border: 2px dashed #bdc3c7;
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                background: #f8f9fa;
            ">
                <span style="color: #7f8c8d;">Lit non configuré</span>
            </div>
            """

        html += "</div>"
        return html


# Configuration de l'en-tête et du style de l'admin
admin.site.site_header = "Configuration Hospitalière - Gestion des Chambres et Lits"
admin.site.site_title = "Administration Hospitalière"
admin.site.index_title = "Configuration des Services d'Hospitalisation"

# CSS personnalisé pour l'interface admin
ADMIN_CSS = """
<style>
.bed-grid .bed-item.occupied {
    border-color: #e74c3c !important;
    background-color: #ffeaea !important;
}

.bed-grid .bed-item.available {
    border-color: #27ae60 !important;
    background-color: #eafaf1 !important;
}

.bed-grid .bed-item.maintenance {
    border-color: #f39c12 !important;
    background-color: #fef9e7 !important;
}

.bed-grid .bed-item.inactive {
    border-color: #95a5a6 !important;
    background-color: #f5f6fa !important;
}

.configuration-tools {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 5px;
    padding: 15px;
    margin: 10px 0;
}

.status-indicator {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 5px;
}

.admin-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.admin-actions .button {
    padding: 8px 16px;
    border-radius: 4px;
    text-decoration: none;
    font-weight: bold;
    border: none;
    cursor: pointer;
}
</style>
"""


# Fonction utilitaire pour l'export des données
def export_room_configuration_csv(queryset):
    """Exporte la configuration des chambres en CSV"""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="configuration_chambres.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            "Service",
            "Chambre",
            "Étage",
            "Type",
            "Capacité",
            "Lits Configurés",
            "Lits Actifs",
            "Taux Occupation",
            "Statut",
        ]
    )

    for room in queryset:
        writer.writerow(
            [
                room.service.name,
                room.room_number,
                room.floor,
                room.get_room_type_display(),
                room.bed_capacity,
                room.beds.count(),
                room.beds.filter(is_active=True).count(),
                f"{room.occupancy_rate}%",
                "Actif" if room.is_active else "Inactif",
            ]
        )

    return response


# Signaux pour la gestion automatique
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver


@receiver(post_save, sender=Room)
def room_post_save(sender, instance, created, **kwargs):
    """Actions automatiques après sauvegarde d'une chambre"""
    if created:
        # Log de création
        print(
            f"Nouvelle chambre créée: {instance.room_number} - {instance.service.name}"
        )


@receiver(pre_delete, sender=Room)
def room_pre_delete(sender, instance, **kwargs):
    """Vérifications avant suppression d'une chambre"""
    occupied_beds = instance.beds.filter(is_occupied=True).count()
    if occupied_beds > 0:
        raise Exception(
            f"Impossible de supprimer la chambre {instance.room_number}: {occupied_beds} lit(s) occupé(s)"
        )


@receiver(post_save, sender=Bed)
def bed_post_save(sender, instance, created, **kwargs):
    """Actions automatiques après sauvegarde d'un lit"""
    if created:
        # Marquer automatiquement comme nettoyé lors de la création
        if not instance.last_cleaned:
            instance.last_cleaned = timezone.now()
            instance.save(update_fields=["last_cleaned"])
