# medical/admin.py
from django.contrib import admin
from .models import Medecin
from django.contrib import admin
from .models import Medecin
from finance.models import PrixSupplementaireConfig



class PrixSupplementaireConfigInline(admin.StackedInline):
    model = PrixSupplementaireConfig
    extra = 0
    max_num = 1


@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    list_display = ("nom_complet", "specialite", "disponible")
    inlines = (PrixSupplementaireConfigInline,)
    search_fields = ("personnel__user__first_name", "personnel__user__last_name")
    list_filter = ("disponible", "specialite")
