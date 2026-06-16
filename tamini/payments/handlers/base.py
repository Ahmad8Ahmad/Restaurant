from django.http import JsonResponse


class PaymentHandler:
    code = ''
    name = ''

    def __init__(self, gateway):
        self.gateway = gateway
        self.config = gateway.config or {}

    def checkout(self, request, order):
        raise NotImplementedError

    def success(self, request, order):
        raise NotImplementedError

    def cancel(self, request, order):
        raise NotImplementedError

    def webhook(self, request):
        return JsonResponse({'status': 'ignored'})


_registry = {}

def register_handler(handler_cls):
    _registry[handler_cls.code] = handler_cls

def get_handler(gateway):
    cls = _registry.get(gateway.code)
    if cls:
        return cls(gateway)
    return None
