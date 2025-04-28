# medical/templatetags/app_filters.py
from django import template
from django.template.defaultfilters import stringfilter
import ast

register = template.Library()


@register.filter(name="filter_attr")
def filter_attr(items, filter_str):
    """
    Filtre une liste d'objets selon un attribut et une valeur
    Syntaxe : {{ items|filter_attr:"attribute:value" }}
    """
    if not items:
        return []

    attribute, value = filter_str.split(":", 1)

    # Conversion des valeurs spéciales
    try:
        parsed_value = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        parsed_value = value

    return [item for item in items if getattr(item, attribute, None) == parsed_value]
