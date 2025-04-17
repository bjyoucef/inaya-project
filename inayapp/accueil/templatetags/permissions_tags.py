# accueil/templatetags/permissions_tags.py
from django import template

register = template.Library()

@register.filter(name="has_privilege")
def has_privilege(user, permission_codename):
    return user.has_perm(permission_codename) if permission_codename else True


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
