from django.apps import AppConfig




class OrdersConfig(AppConfig):
    name = 'orders'
    verbose_name = 'الطلبات'

    def ready(self):
        import orders.signals