from django.contrib import admin
from .models import MenuGroup, MenuItems, Theme


class MenuItemsAdmin(admin.ModelAdmin):
    ordering = ("n",)  # Ordonne par le champ n (ordre croissant)


class MenuGroupAdmin(admin.ModelAdmin):
    ordering = ("order",)  # Ordonne par le champ n (ordre croissant)


admin.site.register(MenuItems, MenuItemsAdmin)
admin.site.register(MenuGroup, MenuGroupAdmin)


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("user", "theme")
    search_fields = ("user__username",)
