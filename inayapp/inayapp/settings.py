from decimal import Decimal
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-!en%k-ktxrmpr7mz=q#uu9p3on!iy2fn)uxg2(f_73f+(60@wf"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "192.168.10.0/24",  # autoriser tout le réseau (moins sécurisé) :
    "192.168.0.0/24",  # autoriser tout le réseau (moins sécurisé) :
]
# Application definition

INSTALLED_APPS = [
    "jazzmin",
    "fontawesomefree",
    "nested_admin",
    "widget_tweaks",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "filer",
    "easy_thumbnails",
    "mptt",
    "django_ckeditor_5",
    "simple_history",
    "crispy_forms",
    "crispy_bootstrap5",
    "import_export",
    "rest_framework",
    "django_extensions",
]
INSTALLED_APPS += [
    "audit",
    "accueil",
    "helpdesk",
    "annuaire",
    "rh",
    "documents",
    "finance",
    "patients",
    "medecin.apps.MedecinConfig",
    "medical.apps.MedicalConfig",
    "pharmacies",
    "export_data",
    "inventaire",
    "hospitalisations",
]
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
THUMBNAIL_HIGH_RESOLUTION = True
THUMBNAIL_PROCESSORS = (
    'easy_thumbnails.processors.colorspace',
    'easy_thumbnails.processors.autocrop',
    'easy_thumbnails.processors.scale_and_crop',
    'filer.thumbnail_processors.scale_and_crop_with_subject_location',
    'easy_thumbnails.processors.filters',
)

# settings.py
ANVIZ_CONFIG = {
    'IP': '192.168.10.250',
    'USERNAME': 'admin',
    'PASSWORD': '12345',
    'SESSION_TIMEOUT': 1800  # 30 minutes
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "inayapp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accueil.context_processors.get_menu_groups",
                "accueil.context_processors.get_menu_items",
                "accueil.context_processors.navbar_context",
                "accueil.context_processors.notification",
                "audit.context_processors.audit_stats",
            ],
        },
    },
]

WSGI_APPLICATION = "inayapp.wsgi.application"


MEDIA_URL = "/files/"
MEDIA_ROOT = os.path.join(BASE_DIR, "files")

# Taille max des fichiers (optionnel)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 Mo


X_FRAME_OPTIONS = 'ALLOWALL'

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases


DATABASES = {
    "default": {
        'ENGINE': 'django.db.backends.mysql',  # Django utilise mysqlclient pour MariaDB
        'NAME': 'inaya08',
        'USER': 'root',
        'PASSWORD': '@Dmin1548@',
        'HOST': '127.0.0.1',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "login"

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "fr"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_ROOT = os.path.join(BASE_DIR,'static')
STATIC_URL = "/static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'inayapp/static')]

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


LOGOUT_REDIRECT_URL = '/'


JAZZMIN_SETTINGS = {
    # Titre du site qui apparaît dans l'onglet du navigateur
    "site_title": "INAYA APP",
    # En-tête de la page d'administration
    "site_header": "INAYA APP",
    # Marque affichée dans la barre latérale et dans l'en-tête
    "site_brand": "INAYA APP",
    # Chemin vers le logo affiché dans la barre latérale (relatif au dossier static)
    "site_logo": "\\icon\\logo_inaya.svg",
    # Chemin vers l'icône du site
    "site_icon": "icon/favicon.ico",
    # Message de bienvenue affiché sur la page d'accueil de l'administration
    "welcome_sign": "Bienvenue sur l'administration INAYA APP",
    # Texte de copyright affiché en bas de la page
    "copyright": "© 2025 INAYA APP",
    # Modèle utilisé par la barre de recherche en haut de la page
    "search_model": "auth.User",
    # (Optionnel) Attribut pour afficher l'avatar de l'utilisateur ; laisser à None si non utilisé
    "user_avatar": None,
    # Liens affichés dans le menu supérieur (top menu)
    "topmenu_links": [
        {"name": "App Home", "url": "home"},
        {"app": "auth"},
        {"app": "accueil"},
        {
            "name": "Permissions",
            "url": "permissions_dashboard",
            "permissions": ["auth.view_user"],
        },
    ],
    # Liens dans le menu utilisateur (menu déroulant en haut à droite)
    "usermenu_links": [
        {"name": "Home", "url": "home"},
        {"model": "auth.user"},
    ],
    # Afficher ou non la barre latérale
    "show_sidebar": True,
    # Déployer ou réduire la navigation par défaut
    "navigation_expanded": True,
    # Liste des applications à masquer dans la navigation
    "hide_apps": ["auth", "accueil"],
    # Liste des modèles à masquer dans la navigation
    "hide_models": [],
    # Ordre des applications (les applications non listées seront affichées en dernier)
    # Icône par défaut pour les parents de la navigation (utilise FontAwesome)
    "default_icon_parents": "fas fa-chevron-circle-right",
    # Icône par défaut pour les enfants de la navigation
    "default_icon_children": "fas fa-circle",
    # Active les modales pour les relations (pour un chargement plus fluide)
    "related_modal_active": True,
    # Chemin vers un fichier CSS personnalisé (optionnel)
    "custom_css": "css/custom_jazzmin.css",
    # Chemin vers un fichier JS personnalisé (optionnel)
    "custom_js": None,
    # Afficher ou non l'outil de configuration de l'interface utilisateur
    "show_ui_builder": True,
    # Format par défaut pour les formulaires de changement (ex. "horizontal_tabs", "vertical_tabs", "collapsible")
    "changeform_format": "horizontal_tabs",
    # Surcharges spécifiques pour certains modèles
    "changeform_format_overrides": {
        "auth.user": "horizontal_tabs",
    },
    # Configuration spécifique pour les permissions
    "custom_links": {
        "auth": [
            {
                "name": "Gestion des Utilisateurs",
                "url": "user_permissions_list",
                "icon": "fas fa-users-cog",
                "permissions": ["auth.view_user"],
            },
            {
                "name": "Gestion des Groupes",
                "url": "group_permissions_list",
                "icon": "fas fa-layer-group",
                "permissions": ["auth.view_group"],
            },
            {
                "name": "Permissions Détaillées",
                "url": "admin:auth_permission_changelist",
                "icon": "fas fa-shield-alt",
                "permissions": ["auth.view_permission"],
            },
        ]
    },  # Icônes personnalisées pour les modèles d'authentification
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.User": "fas fa-user",
        "auth.Group": "fas fa-users",
        "auth.Permission": "fas fa-key",
    },
    # Ordre d'affichage des applications
    "order_with_respect_to": [
        "medical",
        "patients",
        "medecin",
        # ... autres apps
    ],
    # Configuration avancée pour les permissions
    "changeform_format_overrides": {
        "auth.user": "horizontal_tabs",
        "auth.group": "horizontal_tabs",
        "auth.permission": "single",
    },
}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": True,
    "footer_small_text": True,
    "body_small_text": False,
    "brand_small_text": True,
    "brand_colour": False,
    "accent": "accent-indigo",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": True,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": True,
    "sidebar_fixed": True,
    "sidebar_nav_small_text": True,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": True,
    "sidebar_nav_legacy_style": True,
    "sidebar_nav_flat_style": True,
    "theme": "default",
    "dark_mode_theme": None,
    # Couleurs pour les permissions
    "accent": "accent-primary",
    "navbar": "navbar-dark navbar-primary",
    "sidebar": "sidebar-dark-primary",
    # Boutons personnalisés
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
    "actions_sticky_top": True,
}
PLOTLY_OFFLINE_CONFIG = {"show_link": False, "link_text": "", "displaylogo": False}


CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"


# Configuration d'audit (optionnel)
AUDIT_SETTINGS = {
    "TRACK_ANONYMOUS_USERS": False,
    # "EXCLUDE_APPS": ["sessions", "admin", "contenttypes", "auth"],
    # "EXCLUDE_MODELS": ["auth.Permission", "contenttypes.ContentType"],
    "MAX_LOG_AGE_DAYS": 365,
    "ENABLE_API_AUDIT": True,
}

# ============================================
# CONFIGURATION MULTI-CACHE DANS SETTINGS.PY
# ============================================

# settings.py

CACHES = {
    # Cache par défaut - Mémoire (rapide pour données fréquentes)
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
        "TIMEOUT": 300,  # 5 minutes
        "OPTIONS": {
            "MAX_ENTRIES": 500,
            "CULL_FREQUENCY": 3,
        },
    },
    # Cache base de données (persistant pour données importantes)
    "database": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table_persistent",
        "TIMEOUT": 86400,  # 24 heures
        "OPTIONS": {
            "MAX_ENTRIES": 2000,
            "CULL_FREQUENCY": 4,
        },
    },
    # Cache session (pour données utilisateur)
    "session": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table_sessions",
        "TIMEOUT": 1800,  # 30 minutes
    },
    # Cache court terme (pour calculs rapides)
    "quick": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "quick-cache",
        "TIMEOUT": 60,  # 1 minute
        "OPTIONS": {
            "MAX_ENTRIES": 100,
        },
    },
    # Cache long terme (pour données rarement modifiées)
    "longterm": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table_longterm",
        "TIMEOUT": 604800,  # 7 jours
    },
}


# Configuration des sessions pour utiliser le cache
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "session"
# Configuration de la base de données pour le cache
# Assurez-vous d'avoir créé la table de cache dans votre base de données
