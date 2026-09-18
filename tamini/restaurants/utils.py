"""Helpers for restaurant-owner views.

An owner may manage several restaurants.  These helpers resolve which
one the owner is currently acting on and remember that choice in the
session so follow-up form POSTs (which carry no query string) stay on
the same restaurant.
"""
from django.utils.translation import gettext as _

from .models import Restaurant


def resolve_current_restaurant(request, create=False):
    """Resolve which of ``request.user``'s restaurants is selected.

    Priority: ``?restaurant=<id>`` query param, then the
    ``current_restaurant_id`` session value, then the owner's first
    restaurant.  When ``create`` is true, an owner with no restaurants
    gets a placeholder restaurant created (dashboard auto-provision).
    """
    owned = Restaurant.objects.filter(owner=request.user)

    rid = request.GET.get('restaurant')
    if not rid:
        rid = request.session.get('current_restaurant_id')
    if rid is not None:
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            rid = None
    if rid is not None:
        restaurant = owned.filter(id=rid).first()
    else:
        restaurant = None

    if restaurant is None:
        restaurant = owned.first()

    if restaurant is None and create:
        restaurant = Restaurant.objects.create(
            owner=request.user,
            name=_("مطعم %(username)s") % {'username': request.user.username},
            is_approved=False,
        )

    if restaurant is not None:
        request.session['current_restaurant_id'] = restaurant.id
    return restaurant