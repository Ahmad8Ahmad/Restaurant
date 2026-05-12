from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@receiver(post_save, sender=Order)
def send_order_notification(sender, instance, created, **kwargs):
    if created:
        # 1. بنوصل لصاحب المطعم من خلال الطلب
        # تأكد إن موديل Order فيه حقل اسمه restaurant ومنه بنجيب الـ owner
        owner = instance.restaurant.owner 
        
        # 2. بنحدد اسم المجموعة الخاصة بصاحب المطعم
        group_name = f"order_notif_{owner.id}"
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_name, # هون السحر! الإرسال فقط لهذا الشخص
            {
                'type': 'send_notification',
                'message': f'لديك طلب جديد رقم {instance.id} من {instance.restaurant.name}'
            }
        )
