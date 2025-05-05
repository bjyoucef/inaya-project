from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import MenuGroup, MenuItem, NavbarItem


class NavbarItemInline(admin.TabularInline):
    model = NavbarItem
    extra = 0
    fields = ("type", "label", "icon", "url_name", "order", "permission", "preview")
    readonly_fields = ("preview",)
    ordering = ("order",)

    def preview(self, obj):
        if obj.pk:
            url = reverse(
                "admin:%s_%s_change" % (obj._meta.app_label, obj._meta.model_name),
                args=[obj.pk],
            )
            return format_html('<a class="button" href="{}">✎ Éditer</a>', url)
        return "-"

    preview.short_description = "Actions"


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    fields = ("label", "route", "icon", "order", "permission", "navbar_items_link")
    readonly_fields = ("navbar_items_link",)
    ordering = ("order",)
    show_change_link = True

    def navbar_items_link(self, obj):
        count = obj.navbar_items.count()
        url = (
            reverse(
                "admin:%s_%s_changelist"
                % (NavbarItem._meta.app_label, NavbarItem._meta.model_name)
            )
            + f"?menu_item__id__exact={obj.id}"
        )
        return format_html(
            '<a class="button" href="{}">{} éléments de navigation</a>', url, count
        )

    navbar_items_link.short_description = "Éléments associés"


@admin.register(MenuGroup)
class MenuGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "icon_preview", "order", "permission", "menu_items_count")
    list_editable = ("order",)
    search_fields = ("name", "permission")
    inlines = (MenuItemInline,)
    ordering = ("order",)

    def icon_preview(self, obj):
        return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)

    icon_preview.short_description = "Icône"

    def menu_items_count(self, obj):
        return obj.items.count()

    menu_items_count.short_description = "Éléments"


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "group",
        "route",
        "icon_preview",
        "order",
        "permission",
        "navbar_items_count",
    )
    list_editable = ("order",)
    list_filter = ("group",)
    search_fields = ("label", "route", "permission")
    inlines = (NavbarItemInline,)
    autocomplete_fields = ("group",)
    ordering = ("order",)

    def icon_preview(self, obj):
        return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)

    icon_preview.short_description = "Icône"

    def navbar_items_count(self, obj):
        return obj.navbar_items.count()

    navbar_items_count.short_description = "Éléments Navbar"


@admin.register(NavbarItem)
class NavbarItemAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "type",
        "icon_preview",
        "menu_item",
        "url_name",
        "order",
        "permission",
    )
    list_editable = ("order", "type")
    list_filter = ("type", "menu_item")
    search_fields = ("label", "url_name", "permission")
    autocomplete_fields = ("menu_item",)
    ordering = ("order",)

    def icon_preview(self, obj):
        if obj.icon:
            return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)
        return "-"

    icon_preview.short_description = "Icône"
