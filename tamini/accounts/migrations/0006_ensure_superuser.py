from django.db import migrations
from django.contrib.auth.hashers import make_password


def update_superuser(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    new_email = 'ahmad19.8722.2@gmail.com'
    old_email = 'taminyfood@gmail.com'
    password = 'admin123'

    new_user = User.objects.filter(email=new_email).first()
    if new_user:
        new_user.is_staff = True
        new_user.is_superuser = True
        new_user.password = make_password(password)
        new_user.save()
        User.objects.filter(email=old_email).delete()
        return

    old_user = User.objects.filter(email=old_email).first()
    if old_user:
        old_user.email = new_email
        old_user.username = 'admin'
        old_user.password = make_password(password)
        old_user.is_staff = True
        old_user.is_superuser = True
        old_user.save()
        return

    User.objects.create(
        email=new_email,
        username='admin',
        password=make_password(password),
        is_staff=True,
        is_superuser=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_create_superuser'),
    ]

    operations = [
        migrations.RunPython(update_superuser, migrations.RunPython.noop),
    ]
