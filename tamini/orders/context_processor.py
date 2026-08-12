from .models import Cart


def cart_count_processor(request):
    """Read-only cart lookup for the navbar/cart drawer.

    Never creates a session or a Cart row here — that only happens when the
    user actually adds something to the cart. Otherwise every anonymous page
    view writes to the session + DB for no reason.
    """
    count = 0
    items = {}
    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user, session_key=None).first()
        elif request.session.session_key:
            cart = Cart.objects.filter(
                user=None,
                session_key=request.session.session_key,
            ).first()
        else:
            cart = None
        if cart is not None:
            count = cart.total_quantity()
            for ci in cart.items.select_related('menu_item__restaurant'):
                mi = ci.menu_item
                items[str(mi.id)] = {
                    'name': mi.name,
                    'price': float(mi.discount_price if mi.discount_price else mi.price),
                    'quantity': ci.quantity,
                    'image': mi.image.url if mi.image else None,
                    'restaurant_id': mi.restaurant.id,
                }
    except Exception:
        count = 0
        items = {}
    return {
        'global_cart_count': count,
        'cart_items': items,
    }