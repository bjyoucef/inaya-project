from django.contrib import admin
from .models import MenuItems


class MenuItemsAdmin(admin.ModelAdmin):
    ordering = ("n",)  # Ordonne par le champ n (ordre croissant)


admin.site.register(MenuItems, MenuItemsAdmin)
