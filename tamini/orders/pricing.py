"""Single source of truth for order pricing.

Every checkout path (web cart, web checkout, the DRF API and the driver's
earnings figure) must agree on what an order costs. Previously each site
recomputed the fee independently, so the API charged a flat base fee with no
distance or service fee while the web charged base + per-km + 5% -- the same
basket cost two different amounts depending on which client placed it.
"""
from django.conf import settings

from support.models import SiteSettings
from tamini.utils import haversine_km

DEFAULT_BASE_FEE = 200
DEFAULT_PER_KM_FEE = 1500
SERVICE_FEE_RATE = 0.05


def site_fees():
    """(base_fee, per_km_fee) from admin-configurable site settings."""
    site = SiteSettings.get_settings()
    return (
        site.get('delivery_base_fee', DEFAULT_BASE_FEE),
        site.get('delivery_per_km_fee', DEFAULT_PER_KM_FEE),
    )


def delivery_fee(restaurant, lat, lng, fallback=None):
    """Delivery fee for a basket going to (lat, lng) from *restaurant*.

    Falls back to ``settings.DELIVERY_FEE`` when either end of the trip is
    ungeocoded, since distance is unknowable. *fallback* overrides that.
    """
    if fallback is None:
        fallback = getattr(settings, 'DELIVERY_FEE', 5000)
    if restaurant is None:
        return fallback
    if not restaurant.latitude or not restaurant.longitude:
        return fallback
    if lat is None or lng is None:
        return fallback

    try:
        distance = haversine_km(
            float(lat), float(lng),
            float(restaurant.latitude), float(restaurant.longitude),
        )
    except (TypeError, ValueError):
        return fallback

    base_fee, per_km_fee = site_fees()
    return round(base_fee + (distance * per_km_fee))


def service_fee(subtotal, rate=SERVICE_FEE_RATE):
    return round(float(subtotal) * rate, 2)


def quote(subtotal, restaurant=None, lat=None, lng=None, fallback=None):
    """Full price breakdown for a basket.

    Returns a dict with ``subtotal``, ``delivery_fee``, ``service_fee`` and
    ``total`` so callers that render a breakdown stay consistent with the
    amount actually charged.
    """
    subtotal = float(subtotal or 0)
    fee = delivery_fee(restaurant, lat, lng, fallback=fallback)
    service = service_fee(subtotal)
    return {
        'subtotal': subtotal,
        'delivery_fee': fee,
        'service_fee': service,
        'total': subtotal + fee + service,
    }
