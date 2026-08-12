import threading
import logging
import math

logger = logging.getLogger(__name__)


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. ~10x faster than geopy's geodesic and
    plenty accurate for delivery proximity display."""
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return radius * 2 * math.asin(math.sqrt(a))


def send_mail_async(subject, text, from_email, recipient_list, html_message=None):
    from django.core.mail import send_mail
    def _send():
        try:
            sent = send_mail(subject, text, from_email, recipient_list, html_message=html_message)
            if not sent:
                logger.warning("send_mail returned False for %s", recipient_list)
        except Exception as e:
            logger.error("send_mail failed for %s: %s", recipient_list, e)
    t = threading.Thread(target=_send, daemon=True)
    t.start()
