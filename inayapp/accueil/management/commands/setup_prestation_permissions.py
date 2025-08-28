# medical/management/commands/setup_prestation_permissions.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "Créer les groupes et assigner les permissions pour les prestations KT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--list-permissions",
            action="store_true",
            help="Lister toutes les permissions medical disponibles",
        )

    def handle(self, *args, **options):
        if options["list_permissions"]:
            self._list_medical_permissions()
            return

        # Définition des groupes et leurs permissions avec le modèle spécifique
        groups_permissions = {
            "Médecins KT": [
                # Prestations - Consultation et création (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "add_prestationkt"),
                ("medical", "prestationkt", "planifier_prestationkt"),
                ("medical", "prestationkt", "realiser_prestationkt"),
                ("medical", "prestationkt", "view_patient_history"),
                # Actes - Consultation (actekt)
                ("medical", "actekt", "view_tarifs_acte"),
                ("medical", "actekt", "view_produits_acte"),
                # Détails facturation (prestationacte)
                ("medical", "prestationacte", "view_facturation_details"),
            ],
            "Secrétaires KT": [
                # Prestations - Gestion complète (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "add_prestationkt"),
                ("medical", "prestationkt", "change_prestationkt"),
                ("medical", "prestationkt", "planifier_prestationkt"),
                ("medical", "prestationkt", "view_all_prestationkt"),
                ("medical", "prestationkt", "view_patient_history"),
                ("medical", "prestationkt", "export_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
                # Actes - Consultation (actekt)
                ("medical", "actekt", "view_tarifs_acte"),
                ("medical", "actekt", "view_produits_acte"),
            ],
            "Administrateurs KT": [
                # Prestations - Toutes permissions (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "add_prestationkt"),
                ("medical", "prestationkt", "change_prestationkt"),
                ("medical", "prestationkt", "delete_prestationkt"),
                ("medical", "prestationkt", "planifier_prestationkt"),
                ("medical", "prestationkt", "realiser_prestationkt"),
                ("medical", "prestationkt", "payer_prestationkt"),
                ("medical", "prestationkt", "annuler_prestationkt"),
                ("medical", "prestationkt", "view_all_prestationkt"),
                ("medical", "prestationkt", "export_prestationkt"),
                ("medical", "prestationkt", "change_status_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
                ("medical", "prestationkt", "view_patient_history"),
                # Actes - Gestion complète (actekt)
                ("medical", "actekt", "view_tarifs_acte"),
                ("medical", "actekt", "manage_tarifs_acte"),
                ("medical", "actekt", "view_produits_acte"),
                # Prestations Acte - Facturation (prestationacte)
                ("medical", "prestationacte", "facturer_prestationacte"),
                ("medical", "prestationacte", "payer_prestationacte"),
                ("medical", "prestationacte", "rejeter_prestationacte"),
                ("medical", "prestationacte", "view_facturation_details"),
                ("medical", "prestationacte", "manage_conventions"),
                # Tarifs (tarifacte)
                ("medical", "tarifacte", "set_default_tarif"),
                ("medical", "tarifacte", "view_all_tarifs"),
                ("medical", "tarifacte", "manage_tarifs_history"),
                # Paiements espèces (prestationacte)
                ("medical", "prestationacte", "manage_paiements_especes"),
                ("medical", "prestationacte", "view_paiements_especes"),
                ("medical", "prestationacte", "encaisser_especes"),
                ("medical", "prestationacte", "supprimer_paiements_especes"),
            ],
            "Comptables KT": [
                # Prestations - Consultation et paiement (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "payer_prestationkt"),
                ("medical", "prestationkt", "view_all_prestationkt"),
                ("medical", "prestationkt", "export_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
                # Facturation (prestationacte)
                ("medical", "prestationacte", "facturer_prestationacte"),
                ("medical", "prestationacte", "payer_prestationacte"),
                ("medical", "prestationacte", "rejeter_prestationacte"),
                ("medical", "prestationacte", "view_facturation_details"),
                ("medical", "prestationacte", "manage_conventions"),
                # Tarifs - Consultation (tarifacte et actekt)
                ("medical", "tarifacte", "view_all_tarifs"),
                ("medical", "actekt", "view_tarifs_acte"),
                # Paiements espèces (prestationacte)
                ("medical", "prestationacte", "view_paiements_especes"),
                ("medical", "prestationacte", "encaisser_especes"),
            ],
            "Superviseurs KT": [
                # Prestations - Supervision et validation (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "change_prestationkt"),
                ("medical", "prestationkt", "realiser_prestationkt"),
                ("medical", "prestationkt", "payer_prestationkt"),
                ("medical", "prestationkt", "annuler_prestationkt"),
                ("medical", "prestationkt", "view_all_prestationkt"),
                ("medical", "prestationkt", "export_prestationkt"),
                ("medical", "prestationkt", "change_status_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
                ("medical", "prestationkt", "view_patient_history"),
                # Facturation (prestationacte)
                ("medical", "prestationacte", "facturer_prestationacte"),
                ("medical", "prestationacte", "payer_prestationacte"),
                ("medical", "prestationacte", "rejeter_prestationacte"),
                ("medical", "prestationacte", "view_facturation_details"),
                ("medical", "prestationacte", "manage_conventions"),
                # Consultation des tarifs (tarifacte et actekt)
                ("medical", "tarifacte", "view_all_tarifs"),
                ("medical", "actekt", "view_tarifs_acte"),
                # Paiements espèces (prestationacte)
                ("medical", "prestationacte", "manage_paiements_especes"),
                ("medical", "prestationacte", "view_paiements_especes"),
                ("medical", "prestationacte", "encaisser_especes"),
            ],
            "Facturation KT": [
                # Gestion des conventions (prestationacte)
                ("medical", "prestationacte", "manage_conventions"),
                ("medical", "prestationacte", "view_facturation_details"),
                ("medical", "prestationacte", "facturer_prestationacte"),
                ("medical", "prestationacte", "payer_prestationacte"),
                ("medical", "prestationacte", "rejeter_prestationacte"),
                # Consultation (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "actekt", "view_tarifs_acte"),
            ],
            "Encaissement KT": [
                # Paiements espèces (prestationacte)
                ("medical", "prestationacte", "manage_paiements_especes"),
                ("medical", "prestationacte", "view_paiements_especes"),
                ("medical", "prestationacte", "encaisser_especes"),
                # Consultation (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
            ],
            "Superviseurs Facturation KT": [
                # Toutes les permissions de facturation (prestationacte)
                ("medical", "prestationacte", "manage_conventions"),
                ("medical", "prestationacte", "view_facturation_details"),
                ("medical", "prestationacte", "facturer_prestationacte"),
                ("medical", "prestationacte", "payer_prestationacte"),
                ("medical", "prestationacte", "rejeter_prestationacte"),
                ("medical", "prestationacte", "manage_paiements_especes"),
                ("medical", "prestationacte", "view_paiements_especes"),
                ("medical", "prestationacte", "encaisser_especes"),
                ("medical", "prestationacte", "supprimer_paiements_especes"),
                # Prestations (prestationkt)
                ("medical", "prestationkt", "view_prestationkt"),
                ("medical", "prestationkt", "change_prestationkt"),
                ("medical", "prestationkt", "generate_bon_paiement"),
                ("medical", "prestationkt", "export_prestationkt"),
            ],
        }

        created_groups = 0
        assigned_permissions = 0
        failed_permissions = []

        for group_name, permission_tuples in groups_permissions.items():
            # Créer ou récupérer le groupe
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                created_groups += 1
                self.stdout.write(self.style.SUCCESS(f"Groupe créé: {group_name}"))
            else:
                self.stdout.write(f"Groupe existant: {group_name}")

            # Assigner les permissions
            for app_label, model_name, codename in permission_tuples:
                try:
                    # Rechercher la permission avec le modèle spécifique
                    permission = Permission.objects.get(
                        codename=codename,
                        content_type__app_label=app_label,
                        content_type__model=model_name,
                    )

                    group.permissions.add(permission)
                    assigned_permissions += 1

                except Permission.DoesNotExist:
                    perm_str = f"{app_label}.{codename} ({model_name})"
                    failed_permissions.append(perm_str)
                    self.stdout.write(
                        self.style.WARNING(f"Permission non trouvée: {perm_str}")
                    )
                except Exception as e:
                    perm_str = f"{app_label}.{codename} ({model_name})"
                    failed_permissions.append(perm_str)
                    self.stdout.write(
                        self.style.ERROR(f"Erreur pour {perm_str}: {str(e)}")
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nRésumé:\n"
                f"- {created_groups} groupes créés\n"
                f"- {assigned_permissions} permissions assignées\n"
                f"- {len(failed_permissions)} permissions non trouvées\n"
                f"- {len(groups_permissions)} groupes configurés au total"
            )
        )

        # Afficher les permissions manquantes
        if failed_permissions:
            self.stdout.write(
                self.style.WARNING(
                    f"\nPermissions manquantes:\n"
                    + "\n".join(f"  - {perm}" for perm in failed_permissions)
                )
            )

        # Afficher les groupes créés
        self.stdout.write("\nGroupes disponibles:")
        for group_name in groups_permissions.keys():
            try:
                group = Group.objects.get(name=group_name)
                perm_count = group.permissions.count()
                self.stdout.write(f"  - {group_name}: {perm_count} permissions")
            except Group.DoesNotExist:
                self.stdout.write(f"  - {group_name}: ERREUR - Groupe non trouvé")

        self.stdout.write(
            self.style.SUCCESS(
                "\n" + "=" * 50 + "\n"
                "SUCCÈS! Groupes et permissions configurés.\n\n"
                "Pour assigner un utilisateur à un groupe:\n"
                'user.groups.add(Group.objects.get(name="Nom du groupe"))\n\n'
                "Ou via l'interface admin Django:\n"
                "Admin > Utilisateurs > Sélectionner un utilisateur > Groupes\n"
                "=" * 50
            )
        )

    def _list_medical_permissions(self):
        """Liste toutes les permissions medical disponibles"""
        self.stdout.write("Permissions medical disponibles:")

        medical_perms = (
            Permission.objects.filter(content_type__app_label="medical")
            .select_related("content_type")
            .order_by("content_type__model", "codename")
        )

        current_model = None
        for perm in medical_perms:
            if current_model != perm.content_type.model:
                current_model = perm.content_type.model
                self.stdout.write(f"\n=== {current_model.upper()} ===")

            self.stdout.write(
                f"  - medical.{perm.codename} ({perm.content_type.model}) - {perm.name}"
            )
