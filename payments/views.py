from django.shortcuts import render, get_object_or_404, redirect
from orders.models import Order
from .models import Payment

def process_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        # Here you would integrate with a payment gateway
        # For simplicity, we will just create a Payment object
        payment, created = Payment.objects.update_or_create(order=order, defaults={'amount': order.total_price, 'payment_method': 'Card', 'transaction_id': 'test_' + str(order.id), 'status': 'Completed'})
        order.status = 'completed'
        order.save()
        return render(request, 'payments/success.html', {'order': order})
    return render(request, 'payments/process.html', {'order': order})


def payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'payments/success.html', {'order': order})
    
