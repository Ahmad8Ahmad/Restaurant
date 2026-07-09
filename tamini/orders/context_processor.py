from .models import Cart


def cart_count_processor(request):
    try:
        cart = Cart.get_for_request(request)
        count = cart.total_quantity()
        items = {}
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