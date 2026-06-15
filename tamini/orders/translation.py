from modeltranslation.translator import translator, TranslationOptions
from .models import Review


class ReviewTranslationOptions(TranslationOptions):
    fields = ('comment',)


translator.register(Review, ReviewTranslationOptions)
