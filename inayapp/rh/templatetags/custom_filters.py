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
