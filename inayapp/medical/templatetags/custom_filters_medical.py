# medical/templatetags/custom_filters_medical.py
import calendar
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def div(value, arg):
    """
    Divise la valeur par l'argument.
    Usage: {{ montant|div:duree }}

    Args:
        value: La valeur à diviser (numérateur)
        arg: Le diviseur

    Returns:
        Le résultat de la division ou 0 si erreur
    """
    try:
        # Convertir les valeurs en Decimal pour plus de précision
        if value is None or arg is None:
            return 0

        # Gérer les cas où les valeurs sont des chaînes vides
        if value == "" or arg == "":
            return 0

        # Convertir en Decimal
        dividend = Decimal(str(value))
        divisor = Decimal(str(arg))

        # Éviter la division par zéro
        if divisor == 0:
            return 0

        # Effectuer la division
        result = dividend / divisor

        # Retourner le résultat en float pour compatibilité avec les templates
        return float(result)

    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        # En cas d'erreur, retourner 0
        return 0


@register.filter
def multiply(value, arg):
    """
    Multiplie la valeur par l'argument.
    Usage: {{ prix|multiply:quantite }}
    """
    try:
        if value is None or arg is None:
            return 0

        if value == "" or arg == "":
            return 0

        value_decimal = Decimal(str(value))
        arg_decimal = Decimal(str(arg))

        result = value_decimal * arg_decimal
        return float(result)

    except (ValueError, TypeError, InvalidOperation):
        return 0


@register.filter
def mul(value, arg):
    """Alias pour multiply - Multiplie deux valeurs"""
    return multiply(value, arg)


@register.filter
def percentage(value, total):
    """
    Calcule le pourcentage de value par rapport au total.
    Usage: {{ partie|percentage:total }}
    """
    try:
        if value is None or total is None:
            return 0

        if value == "" or total == "":
            return 0

        value_decimal = Decimal(str(value))
        total_decimal = Decimal(str(total))

        if total_decimal == 0:
            return 0

        result = (value_decimal / total_decimal) * 100
        return round(float(result), 1)

    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return 0


@register.filter
def subtract(value, arg):
    """
    Soustrait l'argument de la valeur.
    Usage: {{ montant_total|subtract:montant_paye }}
    """
    try:
        if value is None or arg is None:
            return 0

        if value == "" or arg == "":
            return value if value != "" else 0

        value_decimal = Decimal(str(value))
        arg_decimal = Decimal(str(arg))

        result = value_decimal - arg_decimal
        return float(result)

    except (ValueError, TypeError, InvalidOperation):
        return 0


@register.filter
def absolute(value):
    """
    Retourne la valeur absolue.
    Usage: {{ ecart|absolute }}
    """
    try:
        if value is None or value == "":
            return 0

        value_decimal = Decimal(str(value))
        return float(abs(value_decimal))

    except (ValueError, TypeError, InvalidOperation):
        return 0


@register.filter
def round_to(value, decimals):
    """
    Arrondit la valeur au nombre de décimales spécifié.
    Usage: {{ prix|round_to:2 }}
    """
    try:
        if value is None or value == "":
            return 0

        if decimals is None:
            decimals = 0

        value_decimal = Decimal(str(value))
        decimals_int = int(decimals)

        # Créer le format de quantisation
        quantize_exp = (
            Decimal("0." + "0" * decimals_int) if decimals_int > 0 else Decimal("1")
        )

        result = value_decimal.quantize(quantize_exp)
        return float(result)

    except (ValueError, TypeError, InvalidOperation):
        return 0


@register.filter
def currency(value):
    """
    Formate la valeur comme une devise avec séparateurs de milliers.
    Usage: {{ montant|currency }}
    """
    try:
        if value is None or value == "":
            return "0,00"

        value_decimal = Decimal(str(value))

        # Formater avec séparateurs de milliers
        formatted = "{:,.2f}".format(float(value_decimal))

        # Remplacer les séparateurs par ceux utilisés en français
        formatted = formatted.replace(",", " ").replace(".", ",")

        return formatted

    except (ValueError, TypeError, InvalidOperation):
        return "0,00"


@register.filter
def is_positive(value):
    """
    Vérifie si la valeur est positive.
    Usage: {% if ecart|is_positive %}...{% endif %}
    """
    try:
        if value is None or value == "":
            return False

        value_decimal = Decimal(str(value))
        return value_decimal > 0

    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def is_negative(value):
    """
    Vérifie si la valeur est négative.
    Usage: {% if ecart|is_negative %}...{% endif %}
    """
    try:
        if value is None or value == "":
            return False

        value_decimal = Decimal(str(value))
        return value_decimal < 0

    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def duration_format(minutes):
    """
    Formate une durée en minutes vers un format heures:minutes.
    Usage: {{ duree|duration_format }}
    """
    try:
        if minutes is None or minutes == "":
            return "0h00"

        minutes_int = int(float(minutes))

        if minutes_int <= 0:
            return "0h00"

        hours = minutes_int // 60
        remaining_minutes = minutes_int % 60

        if hours > 0:
            return f"{hours}h{remaining_minutes:02d}"
        else:
            return f"{remaining_minutes}min"

    except (ValueError, TypeError):
        return "0h00"


@register.filter
def format_duration(minutes):
    """Alias pour duration_format - Formate une durée en minutes vers heures:minutes"""
    return duration_format(minutes)


@register.filter
def safe_percentage(value, total):
    """
    Calcule un pourcentage de façon sécurisée avec vérification des valeurs nulles.
    Usage: {{ value|safe_percentage:total }}
    """
    try:
        if not value or not total:
            return 0

        value_num = float(value)
        total_num = float(total)

        if total_num == 0:
            return 0

        percentage = (value_num / total_num) * 100
        return round(percentage, 1)

    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def floatformat(value, arg=-1):
    """Import du filtre floatformat de Django pour compatibilité"""
    from django.template.defaultfilters import floatformat as django_floatformat

    return django_floatformat(value, arg)


@register.filter
def sum_attr(queryset, attr):
    """Somme un attribut d'un queryset"""
    try:
        total = Decimal("0.00")
        for obj in queryset:
            value = getattr(obj, attr, 0)
            if value:
                total += Decimal(str(value))
        return total
    except (ValueError, TypeError):
        return Decimal("0.00")


@register.filter
def filter_attr(queryset, filter_expr):
    """Filtre un queryset par attribut:valeur"""
    try:
        attr, value = filter_expr.split(":")
        return [obj for obj in queryset if getattr(obj, attr, None) == value]
    except (ValueError, AttributeError):
        return queryset


@register.filter
def to_int(value):
    """Convertit en entier"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


@register.filter
def get_item(dictionary, key):
    """Récupère un élément d'un dictionnaire"""
    if not dictionary:
        return None
    return dictionary.get(key)


@register.filter
def filter_by_id(queryset, id_value):
    """Filtre un queryset par ID"""
    if not queryset or not id_value:
        return queryset
    try:
        return queryset.filter(id=int(id_value))
    except (ValueError, AttributeError):
        return queryset


@register.filter
def filter_by_status(locations, status):
    """Filtre les locations par statut"""
    if not locations:
        return []
    return [loc for loc in locations if hasattr(loc, "statut") and loc.statut == status]


@register.filter
def dict_get(dictionary, key):
    """Récupère une valeur dans un dictionnaire"""
    if not dictionary or not key:
        return []
    return dictionary.get(key, [])


@register.filter
def dict_values(dictionary):
    """Retourne toutes les valeurs d'un dictionnaire"""
    if not dictionary:
        return []
    return list(dictionary.values())


@register.filter
def sum_lists(list_of_lists):
    """Additionne toutes les listes dans une liste de listes"""
    if not list_of_lists:
        return []
    result = []
    for sublist in list_of_lists:
        if isinstance(sublist, list):
            result.extend(sublist)
    return result


@register.filter
def first_day_of_month(date):
    """Retourne le premier jour du mois"""
    if not date:
        return None
    return date.replace(day=1)


@register.filter
def previous_monday(date):
    """Retourne le lundi précédent ou le même jour si c'est un lundi"""
    if not date:
        return None
    days_since_monday = date.weekday()
    return date - timedelta(days=days_since_monday)


@register.filter
def date_range(start_date, num_days):
    """Génère une liste de dates à partir d'une date de début"""
    if not start_date or not num_days:
        return []

    dates = []
    for i in range(int(num_days)):
        dates.append(start_date + timedelta(days=i))
    return dates


@register.filter
def date_range_month(date):
    """Génère toutes les dates d'un mois"""
    if not date:
        return []

    # Premier et dernier jour du mois
    first_day = date.replace(day=1)
    last_day = first_day.replace(day=calendar.monthrange(date.year, date.month)[1])

    dates = []
    current = first_day
    while current <= last_day:
        dates.append(current)
        current += timedelta(days=1)

    return dates


@register.filter
def month_name(month_number):
    """Retourne le nom du mois à partir du numéro"""
    try:
        month_num = int(month_number)
        if 1 <= month_num <= 12:
            return calendar.month_name[month_num]
    except (ValueError, TypeError):
        pass
    return ""


@register.filter
def make_list(value):
    """Convertit une valeur en liste (équivalent du filtre Django make_list)"""
    return list(str(value))


@register.filter
def is_today(date):
    """Vérifie si une date est aujourd'hui"""
    if not date:
        return False
    return date == timezone.now().date()


@register.filter
def is_past(date):
    """Vérifie si une date est dans le passé"""
    if not date:
        return False
    return date < timezone.now().date()


@register.filter
def is_future(date):
    """Vérifie si une date est dans le futur"""
    if not date:
        return False
    return date > timezone.now().date()


@register.filter
def weekday_name(date):
    """Retourne le nom du jour de la semaine"""
    if not date:
        return ""

    weekdays = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    return weekdays[date.weekday()]


@register.filter
def count_by_status(locations, status):
    """Compte les locations par statut"""
    if not locations:
        return 0
    return len(
        [loc for loc in locations if hasattr(loc, "statut") and loc.statut == status]
    )


@register.filter
def total_locations(locations_dict):
    """Compte le total de locations dans un dictionnaire de listes"""
    if not locations_dict:
        return 0

    total = 0
    for location_list in locations_dict.values():
        if isinstance(location_list, list):
            total += len(location_list)

    return total


@register.filter
def map(queryset, attr):
    """Extrait un attribut de chaque objet dans un queryset"""
    result = []
    for obj in queryset:
        try:
            # Gérer les propriétés et les méthodes
            value = getattr(obj, attr)
            if callable(value):
                value = value()
            result.append(value)
        except AttributeError:
            result.append(0)
    return result


@register.filter
def sum(values):
    """Calcule la somme d'une liste de valeurs"""
    try:
        total = Decimal("0")
        for value in values:
            if value is not None:
                total += Decimal(str(value))
        return total
    except:
        return 0


@register.filter
def truncatechars(value, length):
    """Tronque une chaîne de caractères"""
    if value and len(str(value)) > int(length):
        return str(value)[: int(length) - 3] + "..."
    return value


@register.filter
def stringformat(value, format_spec):
    """Formate une valeur en string"""
    if format_spec == "s":
        return str(value)
    return value


# Tags simples
@register.simple_tag
def calculate_duration_price(bloc, duration):
    """Calcule le prix pour une durée donnée"""
    try:
        return bloc.calculer_prix_location(int(duration))
    except (ValueError, AttributeError):
        return Decimal("0.00")


@register.simple_tag
def calendar_week_dates(date, week_offset=0):
    """Retourne les dates d'une semaine"""
    if not date:
        return []

    # Calculer le début de la semaine (lundi)
    start_of_week = date - timedelta(days=date.weekday())
    start_of_week += timedelta(weeks=week_offset)

    # Générer les 7 jours de la semaine
    week_dates = []
    for i in range(7):
        week_dates.append(start_of_week + timedelta(days=i))

    return week_dates


@register.simple_tag
def get_month_calendar(year, month):
    """Retourne un calendrier pour un mois donné"""
    try:
        year = int(year)
        month = int(month)
        cal = calendar.monthcalendar(year, month)

        # Convertir en objets date
        month_dates = []
        for week in cal:
            week_dates = []
            for day in week:
                if day == 0:
                    week_dates.append(None)
                else:
                    week_dates.append(datetime(year, month, day).date())
            month_dates.append(week_dates)

        return month_dates
    except (ValueError, TypeError):
        return []


# Tags d'inclusion
@register.inclusion_tag("components/price_breakdown.html", takes_context=True)
def show_price_breakdown(context, location):
    """Affiche le détail du calcul de prix"""
    detail = (
        location.get_detail_calcul_prix()
        if hasattr(location, "get_detail_calcul_prix")
        else {}
    )
    return {"detail": detail, "location": location, "request": context.get("request")}


@register.inclusion_tag("components/status_badge.html", takes_context=True)
def status_badge(context, status, size="normal"):
    """Affiche un badge de statut"""
    status_config = {
        "PLANIFIE": {"class": "warning", "icon": "calendar-event"},
        "REALISE": {"class": "success", "icon": "check-circle"},
        "PAYE": {"class": "primary", "icon": "credit-card"},
        "ANNULE": {"class": "danger", "icon": "x-circle"},
        "FORFAIT": {"class": "success", "icon": "tag"},
        "DUREE": {"class": "primary", "icon": "clock"},
    }


    config = status_config.get(status, {"class": "secondary", "icon": "question"})
    return {
        "status": status,
        "config": config,
        "size": size,
        "request": context.get("request"),
    }

@register.filter
def filter_by_status(queryset, status):
    return [item for item in queryset if item.statut == status]
