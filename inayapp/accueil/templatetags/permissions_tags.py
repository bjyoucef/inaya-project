# accueil/templatetags/permissions_tags.py
from django import template


register = template.Library()

@register.filter
def add_numbers(value, arg):
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return


@register.filter
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

@register.filter
def floatval(value):
    """
    Convertit la valeur en float. En cas d’erreur, retourne 0.0.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@register.filter
def ge(value, arg):
    """
    Retourne True si value >= arg (après conversion en float), sinon False.
    Utile pour yesno ou {% if value|ge:100 %}…
    """
    try:
        return float(value) >= float(arg)
    except (TypeError, ValueError):
        return False


@register.simple_tag
def has_permission(user, permission_codename):
    """Vérifie si l'utilisateur a la permission spécifiée"""
    if not permission_codename:
        return True
    return user.has_perm(permission_codename)


@register.simple_tag(takes_context=True)
def group_is_active(context, group):
    request = context["request"]
    user = request.user
    current_path = request.path.rstrip("/")
    for item in group.items.all():
        # Check if user has permission for the item
        if item.permission and not user.has_perm(item.permission):
            continue
        item_route = item.route.rstrip("/")
        # Check if current path matches or is a subpath of the item's route
        if current_path == item_route or current_path.startswith(item_route + "/"):
            return True
    return False


# Add this new template tag
@register.simple_tag(takes_context=True)
def item_is_active(context, item):
    request = context["request"]
    current_path = request.path.rstrip("/")
    item_route = item.route.rstrip("/")
    return current_path == item_route or current_path.startswith(item_route + "/")
