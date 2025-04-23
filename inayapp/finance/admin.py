from django.contrib import admin

from medical.models.actes import Acte

from .models import Convention, Tarif_Gardes,TarifActe,TarifActeConvention

admin.site.register(Tarif_Gardes)


class TarifActeInline(admin.TabularInline):
    model = TarifActe
    extra = 1


@admin.register(Acte)
class ActeAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "service")
    search_fields = ("code", "libelle")
    inlines = [TarifActeInline]


class TarifConventionInline(admin.TabularInline):
    model = TarifActeConvention
    extra = 1


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "active")
    list_filter = ("active",)
    inlines = [TarifConventionInline]
    search_fields = ("nom", "code")
