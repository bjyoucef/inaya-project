"""
# Application Django d'Audit Complète

Cette application fournit un système d'audit complet pour Django qui permet de:
- Traquer toutes les modifications des modèles (création, mise à jour, suppression)
- Enregistrer les connexions/déconnexions des utilisateurs
- Auditer l'accès aux vues et pages
- Générer des rapports d'audit détaillés
- Fournir un tableau de bord d'administration

## Installation

1. Ajoutez 'audit' à INSTALLED_APPS
2. Ajoutez 'audit.middleware.AuditMiddleware' à MIDDLEWARE
3. Exécutez les migrations: `python manage.py makemigrations audit && python manage.py migrate`
4. Configurez l'audit: `python manage.py setup_audit --enable-all`

## Utilisation

### Audit automatique des modèles
```python
from audit.mixins import AuditMixin

class MonModel(AuditMixin, models.Model):
    # Vos champs...
    pass
```

### Audit des vues
```python
from audit.decorators import audit_view

@audit_view
def ma_vue(request):
    # Logique de la vue
    pass
```

### Audit d'actions personnalisées
```python
from audit.decorators import audit_action

@audit_action('EXPORT')
def export_data(request):
    # Logique d'export
    pass
```

## Fonctionnalités

- **Audit automatique**: Utilise les signaux Django pour traquer les modifications
- **Configurations flexibles**: Configurez l'audit par modèle via l'admin
- **Tableau de bord**: Interface d'administration avec graphiques et statistiques
- **Rapports**: Génération de rapports en CSV, JSON
- **Nettoyage**: Commandes pour nettoyer les anciens logs
- **Permissions**: Contrôle d'accès aux données d'audit
- **Performance**: Indexation et optimisation des requêtes

## Commandes de gestion

- `python manage.py setup_audit --enable-all`: Configure l'audit pour tous les modèles
- `python manage.py audit_report --days 30`: Génère un rapport des 30 derniers jours
- `python manage.py cleanup_audit --days 365`: Supprime les logs plus anciens que 365 jours

## Accès au tableau de bord

L'application ajoute automatiquement une section "Audit" à l'admin Django.
Le tableau de bord est accessible via `/admin/audit/` pour les utilisateurs staff.

## Sécurité

- Tous les mots de passe sont exclus automatiquement de l'audit
- Les logs d'audit ne peuvent pas être modifiés via l'admin
- Contrôle d'accès basé sur les permissions Django
- Support des adresses IP derrière des proxies
"""