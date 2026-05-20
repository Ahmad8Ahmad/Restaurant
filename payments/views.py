from django.shortcuts import render, get_object_or_404, redirect
from orders.models import Order
from .models import Payment
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def process_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        payment, created = Payment.objects.update_or_create(order=order, defaults={
            'amount': order.total_price,
            'payment_method': 'Card',
            'transaction_id': 'test_' + str(order.id),
            'status': 'Completed'
        })

        # إشعار المطعم بأن الدفع تم
        try:
            channel_layer = get_channel_layer()
            group_name = f"order_notif_{order.restaurant.owner.id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'message': f'✅ تم الدفع للطلب #{order.id} - جهز الطلب الآن!',
                    'order_id': order.id,
                }
            )
        except Exception as e:
            print(f"WebSocket Error: {e}")

        return render(request, 'payments/success.html', {'order': order})
    return render(request, 'payments/process.html', {'order': order})
    
