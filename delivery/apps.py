from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    name = 'delivery'

    def ready(self):
        import delivery.signals
