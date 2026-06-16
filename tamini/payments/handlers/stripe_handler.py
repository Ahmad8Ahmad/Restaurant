import stripe
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from .base import PaymentHandler, register_handler


class StripeHandler(PaymentHandler):
    code = 'stripe'
    name = 'Stripe'

    def checkout(self, request, order):
        stripe.api_key = self.config.get('secret_key')

        items = []
        for oi in order.items.all():
            items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': oi.menu_item.name},
                    'unit_amount': int(oi.price * 100),
                },
                'quantity': oi.quantity,
            })

        if order.delivery_fee:
            items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': _('رسوم التوصيل')},
                    'unit_amount': int(order.delivery_fee * 100),
                },
                'quantity': 1,
            })

        session = stripe.checkout.Session.create(
            mode='payment',
            line_items=items,
            customer_email=request.user.email if request.user.is_authenticated else None,
            client_reference_id=str(order.id),
            metadata={'order_id': order.id},
            success_url=request.build_absolute_uri(reverse('payments:gateway_success', args=[self.code, order.id])) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(reverse('payments:gateway_cancel', args=[self.code, order.id])),
        )

        from payments.models import Payment
        Payment.objects.update_or_create(order=order, defaults={
            'amount': order.total_price,
            'payment_method': 'Card',
            'gateway_code': 'stripe',
            'transaction_id': session.id,
            'status': 'Pending',
            'stripe_session_id': session.id,
        })

        return redirect(session.url, code=303)

    def success(self, request, order):
        session_id = request.GET.get('session_id')
        from payments.models import Payment
        payment = Payment.objects.filter(order=order, stripe_session_id=session_id).first()
        if not payment:
            payment = Payment.objects.filter(order=order).first()

        if payment and payment.status != 'Completed':
            payment.status = 'Completed'
            payment.save(update_fields=['status'])

        if order.status != 'Confirmed':
            order.status = 'Confirmed'
            order.save(update_fields=['status'])

        from payments.views import _send_notification
        _send_notification(order, _('طلب #%(order_id)s - تم الدفع إلكترونياً! جهز الطلب الآن!') % {'order_id': order.id})

        return None  # signals the view to render success.html

    def cancel(self, request, order):
        from django.contrib import messages
        messages.warning(request, _("تم إلغاء عملية الدفع"))
        return redirect('payments:process', order_id=order.id)

    def webhook(self, request):
        import json
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = self.config.get('webhook_secret', '')

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except (ValueError, stripe.error.SignatureVerificationError):
            from django.http import JsonResponse
            return JsonResponse({'error': 'Invalid signature'}, status=400)

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            order_id = int(session.get('metadata', {}).get('order_id', 0))
            if order_id:
                from orders.models import Order
                from payments.views import _confirm_order
                order = Order.objects.filter(id=order_id).first()
                if order and order.status != 'Confirmed':
                    _confirm_order(order, 'Card', 'stripe', transaction_id=session.get('payment_intent', ''))

        from django.http import JsonResponse
        return JsonResponse({'status': 'ok'})


register_handler(StripeHandler)
