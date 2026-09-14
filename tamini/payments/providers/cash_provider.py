from payments.models import Payment
from payments.providers.base import PaymentProvider


class CashProvider(PaymentProvider):
    value = 'cash'
    name = 'الدفع عند الاستلام'

    def is_enabled(self) -> bool:
        return True

    def create_payment(self, order, amount, currency):
        payment, _created = Payment.objects.update_or_create(
            order=order,
            defaults={
                'amount': amount,
                'method': 'cash',
                'payment_method': 'Cash',
                'provider_ref': '',
                'transaction_id': '',
                'exchange_rate': None,
                'status': 'Pending',
            },
        )
        return payment

    def handle_webhook(self, request) -> bool:
        return False

    def refund(self, payment) -> bool:
        return False