from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from tamini.page_cache import invalidate_shared_pages

from .models import Restaurant, MenuItem, Category, SiteContent, HeroBanner


@receiver(post_save, sender=SiteContent)
def clear_site_content_cache(sender, instance, **kwargs):
    cache.delete('site_content_obj')
    invalidate_shared_pages()


@receiver(post_save, sender=Restaurant)
@receiver(post_save, sender=MenuItem)
@receiver(post_save, sender=Category)
@receiver(post_save, sender=HeroBanner)
def clear_page_cache(sender, instance, **kwargs):
    cache.delete('hero_banner')
    invalidate_shared_pages()
