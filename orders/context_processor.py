from .models import Order
def cart_count_processor(request):
    if request.user.is_authenticated:
        order = Order.objects.filter(customer=request.user, status='Pending').first()
        if order:
            count = sum(item.quantity for item in order.items.all())
            return {'global_cart_count': count}
    return {'global_cart_count': 0}