from django.apps import AppConfig


class RestaurantsConfig(AppConfig):
    name = 'restaurants'
    verbose_name = 'المطاعم'

    def ready(self):
        import restaurants.signals
