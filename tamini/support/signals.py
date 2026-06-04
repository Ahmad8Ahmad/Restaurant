from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import TicketMessage


@receiver(post_save, sender=TicketMessage)
def update_ticket_timestamp(sender, instance, **kwargs):
    instance.ticket.save(update_fields=['updated_at'])
