from django.core.cache import cache
from .models import HeroBanner


def hero_banner_processor(request):
    banner = cache.get('hero_banner')
    if banner is None:
        banner = HeroBanner.objects.filter(is_active=True).first()
        cache.set('hero_banner', banner, 300)
    return {'hero_banner': banner}
