from modeltranslation.translator import translator, TranslationOptions
from .models import Ticket, TicketMessage


class TicketTranslationOptions(TranslationOptions):
    fields = ('subject', 'description')


class TicketMessageTranslationOptions(TranslationOptions):
    fields = ('message',)


translator.register(Ticket, TicketTranslationOptions)
translator.register(TicketMessage, TicketMessageTranslationOptions)
