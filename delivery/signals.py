from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Delivery


@receiver(post_save, sender=Delivery)
def update_order_status(sender, instance, **kwargs):
    order = instance.order
    if instance.status == 'delivered' and order.status != 'Delivered':
        order.status = 'Delivered'
        order.save(update_fields=['status'])
    elif instance.status == 'on_way' and order.status != 'Out for Delivery':
        order.status = 'Out for Delivery'
        order.save(update_fields=['status'])
