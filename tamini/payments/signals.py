from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
from orders.models import Order
from delivery.models import Delivery
from support.models import SiteSettings
from .models import Commission


def _get_rate():
    try:
        return Decimal(SiteSettings.get_settings().get('commission_rate', 12)) / Decimal('100')
    except Exception:
        return Decimal('0.12')


@receiver(post_save, sender=Order)
def create_restaurant_commission(sender, instance, **kwargs):
    if instance.status not in ('Delivered', 'Completed'):
        return
    rate = _get_rate()
    amount = instance.total_price * rate
    defaults = {'amount': amount}
    try:
        if instance.payment.payment_method != 'Cash':
            defaults['is_settled'] = True
            defaults['settled_at'] = timezone.now()
    except Exception:
        pass
    Commission.objects.get_or_create(
        commission_type='restaurant',
        order=instance,
        defaults=defaults
    )


@receiver(post_save, sender=Delivery)
def create_delivery_commission(sender, instance, **kwargs):
    if instance.status != 'delivered':
        return
    rate = _get_rate()
    amount = instance.order.delivery_fee * rate
    defaults = {'amount': amount}
    try:
        if instance.order.payment.payment_method != 'Cash':
            defaults['is_settled'] = True
            defaults['settled_at'] = timezone.now()
    except Exception:
        pass
    Commission.objects.get_or_create(
        commission_type='delivery',
        delivery=instance,
        defaults=defaults
    )
