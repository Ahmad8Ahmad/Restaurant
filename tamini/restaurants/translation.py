from modeltranslation.translator import translator, TranslationOptions
from .models import Restaurant, Category, MenuItem, HeroBanner, SiteContent


class RestaurantTranslationOptions(TranslationOptions):
    fields = ('name', 'description', 'address')


class CategoryTranslationOptions(TranslationOptions):
    fields = ('name',)


class MenuItemTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class HeroBannerTranslationOptions(TranslationOptions):
    fields = ('title', 'subtitle', 'cta_text')


class SiteContentTranslationOptions(TranslationOptions):
    fields = ('welcome_title', 'welcome_subtitle')


translator.register(Restaurant, RestaurantTranslationOptions)
translator.register(Category, CategoryTranslationOptions)
translator.register(MenuItem, MenuItemTranslationOptions)
translator.register(HeroBanner, HeroBannerTranslationOptions)
translator.register(SiteContent, SiteContentTranslationOptions)
