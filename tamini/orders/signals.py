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
        owner = instance.restaurant.owner

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"order_notif_{owner.id}",
                {
                    'type': 'send_notification',
                    'message': f'لديك طلب جديد رقم {instance.id} من {instance.restaurant.name}'
                }
            )
            async_to_sync(channel_layer.group_send)(
                "driver_notifications",
                {
                    'type': 'new_order_available',
                    'message': f'طلب جديد متاح #{instance.id}',
                    'order_id': instance.id
                }
            )
        except Exception:
            pass

        try:
            def _send_push():
                from api.fcm import send_to_user, send_to_role
                title = '🔔 طلب جديد'
                body = f'طلب جديد # {instance.id} من {instance.customer_name or "زبون"}'
                send_to_user(owner, title, body, {'order_id': instance.id, 'type': 'new_order'})
                send_to_role('delivery', 'طلب جديد متاح', f'طلب جديد متاح #{instance.id}', {'order_id': instance.id, 'type': 'new_order'})
            import threading
            threading.Thread(target=_send_push, daemon=True).start()
        except Exception:
            pass


@receiver(post_save, sender='payments.Payment')
def create_ticket_on_payment(sender, instance, created, **kwargs):
    if instance.status == 'Completed' and not hasattr(instance.order, 'ticket'):
        Ticket.objects.create(
            order=instance.order,
            customer=instance.order.customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
