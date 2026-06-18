from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order, Ticket
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@receiver(post_save, sender=Order)
def send_order_notification(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        
        # إشعار صاحب المطعم
        owner = instance.restaurant.owner
        async_to_sync(channel_layer.group_send)(
            f"order_notif_{owner.id}",
            {
                'type': 'send_notification',
                'message': f'لديك طلب جديد رقم {instance.id} من {instance.restaurant.name}'
            }
        )
        
        # إشعار جميع السائقين بطلب جديد متاح
        async_to_sync(channel_layer.group_send)(
            "driver_notifications",
            {
                'type': 'new_order_available',
                'message': f'طلب جديد متاح #{instance.id}',
                'order_id': instance.id
            }
        )


@receiver(post_save, sender='payments.Payment')
def create_ticket_on_payment(sender, instance, created, **kwargs):
    if instance.status == 'Completed' and not hasattr(instance.order, 'ticket'):
        Ticket.objects.create(
            order=instance.order,
            customer=instance.order.customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
