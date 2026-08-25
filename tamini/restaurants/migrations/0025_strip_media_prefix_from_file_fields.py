"""Strip the 'media/' prefix Cloudinary baked into stored file names.

When Cloudinary is the storage backend it prepends the MEDIA_URL prefix
('media/') to every public_id it saves.  Switching to FileSystemStorage
locally then causes double /media/media/ URLs.  This migration removes
the baked-in prefix so file paths match what FileSystemStorage expects.
"""

from django.db import migrations


def strip_prefix(name):
    if name and name.startswith('media/'):
        return name[len('media/'):]
    return name


def forwards(apps, schema_editor):
    # Restaurant logos & covers
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    for r in Restaurant.objects.exclude(logo='').exclude(logo__isnull=True):
        new_name = strip_prefix(r.logo.name)
        if new_name != r.logo.name:
            r.logo.name = new_name
            r.save(update_fields=['logo'])

    for r in Restaurant.objects.exclude(cover_image='').exclude(cover_image__isnull=True):
        new_name = strip_prefix(r.cover_image.name)
        if new_name != r.cover_image.name:
            r.cover_image.name = new_name
            r.save(update_fields=['cover_image'])

    # Hero banners
    HeroBanner = apps.get_model('restaurants', 'HeroBanner')
    for b in HeroBanner.objects.exclude(image='').exclude(image__isnull=True):
        new_name = strip_prefix(b.image.name)
        if new_name != b.image.name:
            b.image.name = new_name
            b.save(update_fields=['image'])

    # Categories
    Category = apps.get_model('restaurants', 'Category')
    for c in Category.objects.exclude(image='').exclude(image__isnull=True):
        new_name = strip_prefix(c.image.name)
        if new_name != c.image.name:
            c.image.name = new_name
            c.save(update_fields=['image'])

    # Menu items
    MenuItem = apps.get_model('restaurants', 'MenuItem')
    for m in MenuItem.objects.exclude(image='').exclude(image__isnull=True):
        new_name = strip_prefix(m.image.name)
        if new_name != m.image.name:
            m.image.name = new_name
            m.save(update_fields=['image'])

    # Support ticket attachments
    TicketMessage = apps.get_model('support', 'TicketMessage')
    for t in TicketMessage.objects.exclude(attachment='').exclude(attachment__isnull=True):
        new_name = strip_prefix(t.attachment.name)
        if new_name != t.attachment.name:
            t.attachment.name = new_name
            t.save(update_fields=['attachment'])


def backwards(apps, schema_editor):
    pass  # Prefix was Cloudinary-specific; no reverse needed.


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0024_restaurant_delivery_fee_and_more'),
        ('support', '0010_alter_ticket_priority_alter_ticket_status_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
