from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from orders.models import Order
from .models import Payment
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils.translation import gettext as _
from support.models import SiteSettings
import stripe
import json


def _stripe_settings():
    site = SiteSettings.get_settings()
    return (
        site.get('stripe_secret_key') or '',
        site.get('stripe_publishable_key') or '',
        site.get('stripe_currency') or 'usd',
        int(site.get('stripe_exchange_rate') or 13000),
    )


def _get_base_url(request):
    return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"


def process_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'Card')

        if payment_method == 'Cash':
            order.status = 'Confirmed'
            order.save()
            Payment.objects.update_or_create(order=order, defaults={
                'amount': order.total_price,
                'payment_method': 'Cash',
                'transaction_id': '',
                'status': 'Pending'
            })
            _send_notification(order, is_cash=True)
            return render(request, 'payments/success.html', {
                'order': order,
                'payment_method': 'Cash',
            })

        elif payment_method == 'Card':
            secret_key, publishable_key, stripe_currency, exchange_rate = _stripe_settings()
            if not secret_key:
                messages.error(request, _("الدفع الإلكتروني غير متاح حالياً"))
                return redirect('payments:process', order_id=order.id)
            stripe.api_key = secret_key
            try:
                unit_amount = int(order.total_price * 100 / exchange_rate) if exchange_rate else 0
                checkout_session = stripe.checkout.Session.create(
                    mode='payment',
                    line_items=[{
                        'price_data': {
                            'currency': stripe_currency,
                            'product_data': {
                                'name': _('طلب #%(id)s') % {'id': order.id},
                                'description': _('طلب من %(name)s') % {'name': order.restaurant.name},
                            },
                            'unit_amount': max(unit_amount, 50),
                        },
                        'quantity': 1,
                    }],
                    client_reference_id=str(order.id),
                    customer_email=request.user.email if request.user.is_authenticated else None,
                    success_url=_get_base_url(request) + '/payments/stripe/success/' + str(order.id) + '/',
                    cancel_url=_get_base_url(request) + '/payments/stripe/cancel/' + str(order.id) + '/',
                )
                order.status = 'Confirmed'
                order.save()
                Payment.objects.update_or_create(order=order, defaults={
                    'amount': order.total_price,
                    'payment_method': 'Card',
                    'transaction_id': checkout_session.id,
                    'status': 'Pending'
                })
                return redirect(checkout_session.url)
            except Exception as e:
                messages.error(request, _("حدث خطأ أثناء الاتصال ببوابة الدفع: %(error)s") % {'error': str(e)})
                return redirect('payments:process', order_id=order.id)

    __, publishable_key, ___, ____ = _stripe_settings()
    return render(request, 'payments/process.html', {
        'order': order,
        'stripe_publishable_key': publishable_key,
    })


def stripe_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    secret_key, _ = _stripe_settings()[:2]
    stripe.api_key = secret_key
    try:
        payment = order.payment
        if payment.transaction_id:
            session = stripe.checkout.Session.retrieve(payment.transaction_id)
            if session.payment_status == 'paid':
                payment.status = 'Completed'
                payment.save()
                _send_notification(order, is_cash=False)
    except Exception:
        pass
    return render(request, 'payments/success.html', {
        'order': order,
        'payment_method': 'Card',
    })


def stripe_cancel(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    Payment.objects.update_or_create(order=order, defaults={
        'amount': order.total_price,
        'status': 'Failed',
    })
    _send_notification(order, is_cash=False)
    messages.error(request, _("تم إلغاء عملية الدفع. يمكنك المحاولة مرة أخرى."))
    return redirect('orders:view_cart')


@csrf_exempt
def stripe_webhook(request):
    secret_key, _ = _stripe_settings()[:2]
    stripe.api_key = secret_key
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret_key)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        order_id = session.get('client_reference_id')
        if order_id:
            try:
                payment = Payment.objects.get(order_id=order_id)
                if payment.status != 'Completed':
                    payment.status = 'Completed'
                    payment.transaction_id = session.get('id', payment.transaction_id)
                    payment.save()
                    _send_notification(payment.order, is_cash=False)
            except Payment.DoesNotExist:
                pass

    return HttpResponse(status=200)


def _send_notification(order, is_cash=False):
    try:
        channel_layer = get_channel_layer()
        group_name = f"order_notif_{order.restaurant.owner.id}"
        message = _('طلب #%(order_id)s - جهز الطلب الآن!') % {'order_id': order.id}
        if is_cash:
            message = _('💰 طلب #%(order_id)s (دفع عند الاستلام) - جهز الطلب الآن!') % {'order_id': order.id}
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'message': message,
                'order_id': order.id,
            }
        )
    except Exception:
        pass
