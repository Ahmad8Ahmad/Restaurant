from .models import HeroBanner


def hero_banner_processor(request):
    banner = HeroBanner.objects.filter(is_active=True).first()
    return {'hero_banner': banner}
