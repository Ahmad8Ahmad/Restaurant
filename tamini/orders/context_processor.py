def cart_count_processor(request):
    cart = request.session.get('cart', {})
    count = request.session.get('cart_count', 0)
    return {
        'global_cart_count': count,
        'cart_items': cart,
    }