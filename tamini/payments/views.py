from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from orders.models import Order
from .models import Payment
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def process_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'Card')
        status = 'Completed'
        transaction_id = ''

        if payment_method == 'Cash':
            transaction_id = ''
            status = 'Pending'
        else:
            transaction_id = 'test_' + str(order.id)
            status = 'Completed'

        order.status = 'Confirmed'
        order.save()

        payment, created = Payment.objects.update_or_create(order=order, defaults={
            'amount': order.total_price,
            'payment_method': payment_method,
            'transaction_id': transaction_id,
            'status': status
        })

        try:
            channel_layer = get_channel_layer()
            group_name = f"order_notif_{order.restaurant.owner.id}"
            message = f'طلب #{order.id} - جهز الطلب الآن!'
            if payment_method == 'Cash':
                message = f'💰 طلب #{order.id} (دفع عند الاستلام) - جهز الطلب الآن!'
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'message': message,
                    'order_id': order.id,
                }
            )
        except Exception as e:
            print(f"WebSocket Error: {e}")

        messages.success(request, "تم استلام طلبك بنجاح! شكراً لطلبك.")
        return redirect('home')
    return render(request, 'payments/process.html', {'order': order})
    
