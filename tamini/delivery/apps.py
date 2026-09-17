from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    name = 'delivery'
    verbose_name = 'التوصيل'

    def ready(self):
        import delivery.signals
