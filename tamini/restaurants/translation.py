from modeltranslation.translator import translator, TranslationOptions
from .models import Restaurant, MenuItem, HeroBanner, SiteContent


class RestaurantTranslationOptions(TranslationOptions):
    fields = ('description', 'address')


class MenuItemTranslationOptions(TranslationOptions):
    fields = ('description',)


class HeroBannerTranslationOptions(TranslationOptions):
    fields = ('title', 'subtitle', 'cta_text')


class SiteContentTranslationOptions(TranslationOptions):
    fields = ('welcome_title', 'welcome_subtitle')


translator.register(Restaurant, RestaurantTranslationOptions)
translator.register(MenuItem, MenuItemTranslationOptions)
translator.register(HeroBanner, HeroBannerTranslationOptions)
translator.register(SiteContent, SiteContentTranslationOptions)
