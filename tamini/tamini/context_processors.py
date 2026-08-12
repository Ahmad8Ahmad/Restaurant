from django.core.cache import cache
from restaurants.models import SiteContent


def site_content(request):
    content = cache.get_or_set('site_content_obj', SiteContent.load, 600)
    return {'site_content': content}
