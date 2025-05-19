from django import template

register = template.Library()


@register.filter
def format_duration(value):
    try:
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        return f"{hours:02d}h {minutes:02d}m"
    except AttributeError:
        return "00h 00m"


@register.filter(expects_localtime=True)
def time(value, fmt):
    try:
        return value.strftime(fmt)
    except AttributeError:
        return "-"


@register.filter(name="status_color")
def status_color(status):
    color_map = {
        "PEN": "warning",
        "APP": "success",
        "REJ": "danger",
        "CAN": "secondary",
    }
    return color_map.get(status, "secondary")


@register.filter
def minutes_to_duree(minutes):
    """
    Convertit un entier de minutes en 'XhYY', ou '-' si <= 0.
    """
    try:
        m = int(minutes)
    except (ValueError, TypeError):
        return "-"
    if m <= 0:
        return "-"
    h = m // 60
    mn = m % 60
    return f"{h}h{mn:02d}"


@register.filter
def first_letter(value):
    return value[0].upper() if value else ""


@register.filter
def is_instance(value, class_name):
    try:
        return value.__class__.__name__.lower() == class_name.lower()
    except AttributeError:
        return False