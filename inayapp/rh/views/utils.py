import logging

logger = logging.getLogger(__name__)


def get_date_range(config):
    """Retourne la plage de dates validée (start_date <= end_date)."""
    start_date, end_date = config.start_date, config.end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date
