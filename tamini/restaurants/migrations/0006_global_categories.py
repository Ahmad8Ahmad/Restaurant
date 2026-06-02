from django.db import migrations, models
import django.db.models.deletion


def copy_restaurant_to_menuitem(apps, schema_editor):
    MenuItem = apps.get_model('restaurants', 'MenuItem')
    for item in MenuItem.objects.select_related('category__restaurant').all():
        if item.category_id and hasattr(item.category, 'restaurant_id') and item.category.restaurant_id:
            item.restaurant_id = item.category.restaurant_id
            item.save(update_fields=['restaurant_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0005_category_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='restaurant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='menu_items', to='restaurants.restaurant'),
        ),
        migrations.RunPython(copy_restaurant_to_menuitem, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='category',
            name='restaurant',
        ),
    ]
