from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
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
