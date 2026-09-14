from django.db import migrations, models


def merge_duplicate_carts(apps, schema_editor):
    """Collapse duplicate carts into the oldest row (merging quantities) so the
    partial unique constraints can be added safely.

    Invariants enforced:
      * one cart per authenticated user  -> (user set, session_key NULL)
      * one cart per guest session       -> (user NULL, session_key set)
    """
    Cart = apps.get_model('orders', 'Cart')

    def collapse(carts):
        if len(carts) <= 1:
            return
        keep = carts[0]
        for dup in carts[1:]:
            for item in dup.items.all():
                current = keep.items.filter(menu_item_id=item.menu_item_id).first()
                if current is not None:
                    current.quantity = min(current.quantity + item.quantity, 99)
                    current.save()
                else:
                    item.cart = keep
                    item.save()
            dup.delete()

    user_ids = Cart.objects.filter(
        user__isnull=False, session_key__isnull=True,
    ).order_by().values_list('user_id', flat=True).distinct()
    for user_id in list(user_ids):
        collapse(list(Cart.objects.filter(
            user_id=user_id, session_key__isnull=True,
        ).order_by('id')))

    keys = Cart.objects.filter(
        user__isnull=True, session_key__isnull=False,
    ).order_by().values_list('session_key', flat=True).distinct()
    for key in keys:
        collapse(list(Cart.objects.filter(
            user__isnull=True, session_key=key,
        ).order_by('id')))


class Migration(migrations.Migration):
    # Non-atomic: SQLite refuses CREATE INDEX in the same transaction as the
    # dedupe DELETEs ("pending trigger events"). Dedupe commits first.
    atomic = False

    dependencies = [
        ('orders', '0015_ticket_orders_tick_custome_c1a14d_idx'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_carts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(('session_key__isnull', True)),
                name='cart_uniq_authenticated_user',
            ),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(
                fields=['session_key'],
                condition=models.Q(('session_key__isnull', False), ('user__isnull', True)),
                name='cart_uniq_guest_session',
            ),
        ),
    ]