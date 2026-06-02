def cart_count_processor(request):
    count = request.session.get('cart_count', 0)
    return {'global_cart_count': count}