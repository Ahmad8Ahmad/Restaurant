from payments.providers.base import PaymentError
from payments.providers.cash_provider import CashProvider
from payments.providers.stripe_provider import StripeProvider

_PROVIDERS = {
    'stripe': StripeProvider,
    'cash': CashProvider,
}


def get_provider(name):
    cls = _PROVIDERS.get((name or '').strip().lower())
    if cls is None:
        return None
    return cls()


def enabled_providers():
    providers = []
    for cls in _PROVIDERS.values():
        provider = cls()
        if provider.is_enabled():
            providers.append(provider)
    providers.sort(key=lambda provider: 0 if provider.value == 'cash' else 1)
    return providers