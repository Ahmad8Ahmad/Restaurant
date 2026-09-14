from django.utils.translation import gettext as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from payments.models import Payment
from payments.providers import get_provider
from payments.providers.base import PaymentError


def initiate_payment(order, method, request=None):
    provider = get_provider(method)
    if provider is None or not provider.is_enabled():
        raise PaymentError(_('طريقة الدفع هذه غير متاحة حالياً'))
    provider.request = request
    payment = provider.create_payment(order, order.total_price, 'usd')
    if provider.value == 'cash':
        mark_payment_completed(payment, is_cash=True)
    return payment


def process_webhook(provider_name, request):
    provider = get_provider(provider_name)
    if provider is None or not provider.is_enabled():
        return False
    return provider.handle_webhook(request)


def mark_payment_completed(payment, is_cash=False):
    order = payment.order
    changed = False
    if payment.status != 'Completed':
        payment.status = 'Completed'
        payment.save(update_fields=['status'])
        changed = True
    if order.status != 'Confirmed':
        order.status = 'Confirmed'
        order.save(update_fields=['status'])
        changed = True
    if changed:
        _send_notification(order, is_cash=is_cash)
    return payment


def mark_payment_failed(payment):
    if payment.status != 'Failed':
        payment.status = 'Failed'
        payment.save(update_fields=['status'])
    return payment


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