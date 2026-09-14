import stripe
from django.db import transaction
from django.utils.translation import gettext as _

from payments.models import Payment
from payments.providers.base import PaymentError, PaymentProvider
from support.models import SiteSettings


class StripeProvider(PaymentProvider):
    value = 'stripe'
    name = 'بطاقة إئتمانية / دفع إلكتروني'

    def __init__(self):
        self._settings = SiteSettings.get_settings()
        self.request = None

    def is_enabled(self) -> bool:
        if self._settings.get('stripe_mode') == 'disabled':
            return False
        return bool(
            self._settings.get('stripe_secret_key')
            and self._settings.get('stripe_publishable_key')
        )

    def create_payment(self, order, amount, currency):
        secret_key = self._settings.get('stripe_secret_key') or ''
        if not secret_key:
            raise PaymentError(_('الدفع الإلكتروني غير متاح حالياً'))
        stripe.api_key = secret_key

        exchange_rate = int(self._settings.get('stripe_exchange_rate') or 13000)
        stripe_currency = self._settings.get('stripe_currency') or currency or 'usd'
        unit_amount = max(int(int(amount) * 100 / exchange_rate), 50)

        base_url = self._base_url()
        if not base_url:
            raise PaymentError(_('الدفع الإلكتروني غير متاح حالياً'))

        customer_email = None
        if self.request is not None:
            user = getattr(self.request, 'user', None)
            if user is not None and user.is_authenticated:
                customer_email = user.email

        try:
            checkout_session = stripe.checkout.Session.create(
                mode='payment',
                line_items=[{
                    'price_data': {
                        'currency': stripe_currency,
                        'product_data': {
                            'name': _('طلب #%(id)s') % {'id': order.id},
                            'description': _('طلب من %(name)s') % {'name': order.restaurant.name},
                        },
                        'unit_amount': unit_amount,
                    },
                    'quantity': 1,
                }],
                client_reference_id=str(order.id),
                customer_email=customer_email,
                success_url=base_url + '/payments/stripe/success/' + str(order.id) + '/',
                cancel_url=base_url + '/payments/stripe/cancel/' + str(order.id) + '/',
            )
        except Exception as exc:
            raise PaymentError(_('حدث خطأ أثناء الاتصال ببوابة الدفع: %(error)s') % {'error': str(exc)})

        payment, created = Payment.objects.update_or_create(
            order=order,
            defaults={
                'amount': amount,
                'method': 'stripe',
                'payment_method': 'Card',
                'provider_ref': checkout_session.id,
                'transaction_id': checkout_session.id,
                'exchange_rate': exchange_rate,
                'status': 'Pending',
            },
        )
        payment.redirect_url = checkout_session.url
        return payment

    def handle_webhook(self, request) -> bool:
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        webhook_secret = self._settings.get('stripe_webhook_secret') or ''
        secret_key = self._settings.get('stripe_secret_key') or ''

        if not webhook_secret or not secret_key:
            return False
        stripe.api_key = secret_key

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError):
            return False

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            order_id = session.get('client_reference_id')
            if order_id:
                try:
                    with transaction.atomic():
                        payment = Payment.objects.select_for_update().get(order_id=order_id)
                        from payments.services import mark_payment_completed
                        mark_payment_completed(payment)
                except Payment.DoesNotExist:
                    pass

        return True

    def refund(self, payment) -> bool:
        return False

    def retrieve_session(self, transaction_id):
        if not transaction_id:
            return None
        secret_key = self._settings.get('stripe_secret_key') or ''
        if not secret_key:
            return None
        stripe.api_key = secret_key
        return stripe.checkout.Session.retrieve(transaction_id)

    def _base_url(self):
        if self.request is None:
            return ''
        return f"{'https' if self.request.is_secure() else 'http'}://{self.request.get_host()}"