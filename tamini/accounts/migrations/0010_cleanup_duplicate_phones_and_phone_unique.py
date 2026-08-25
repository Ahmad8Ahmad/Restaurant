"""Clean up duplicate phones and add unique constraint.

1. Converts empty-string phones to NULL.
2. Deduplicates real phone numbers (keeps most recent user).
3. Adds unique=True to User.phone.
"""

from django.db import migrations, models


def forwards(apps, schema_editor):
    from django.db.models import Count

    User = apps.get_model('accounts', 'User')

    # Convert empty-string phones to NULL.
    User.objects.filter(phone='').update(phone=None)

    # Find duplicate non-null phones and keep only the most recent.
    dupes = (
        User.objects.filter(phone__isnull=False)
        .values('phone')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    for row in dupes:
        phone = row['phone']
        ids = list(
            User.objects.filter(phone=phone)
            .order_by('-date_joined')
            .values_list('id', flat=True)
        )
        for uid in ids[1:]:
            User.objects.filter(pk=uid).update(phone=None)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_user_firebase_uid'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
    ]
