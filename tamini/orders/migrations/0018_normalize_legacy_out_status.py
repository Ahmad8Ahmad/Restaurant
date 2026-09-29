from django.db import migrations

LEGACY = 'Out'
CANONICAL = 'Out for Delivery'


def forwards(apps, schema_editor):
    """Fold legacy 'Out' rows onto the declared 'Out for Delivery' choice.

    orders.views.mark_as_out wrote a bare 'Out', which is not a key in
    Order.STATUS_CHOICES. The value survived in the column (choices are not
    enforced at the DB level) but rendered as a raw untranslated string, was
    rejected by OrderViewSet.update_status, and was invisible to any code
    filtering on the declared choice.
    """
    Order = apps.get_model('orders', 'Order')
    Order.objects.filter(status=LEGACY).update(status=CANONICAL)


def backwards(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    Order.objects.filter(status=CANONICAL).update(status=LEGACY)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0017_alter_cart_options_alter_cartitem_options_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
