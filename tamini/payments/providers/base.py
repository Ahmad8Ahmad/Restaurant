class PaymentError(Exception):
    """Raised when a payment provider cannot complete a payment."""


class PaymentProvider:
    value = ''
    name = ''

    def is_enabled(self) -> bool:
        raise NotImplementedError

    def create_payment(self, order, amount, currency):
        raise NotImplementedError

    def handle_webhook(self, request) -> bool:
        raise NotImplementedError

    def refund(self, payment) -> bool:
        raise NotImplementedError