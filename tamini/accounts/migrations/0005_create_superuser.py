from django.db import migrations

def create_superuser(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    if not User.objects.filter(email='taminyfood@gmail.com').exists():
        User.objects.create_superuser(
            email='taminyfood@gmail.com',
            username='admin',
            password='admin123',
        )

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_user_otp_created_at_alter_user_otp_code'),
    ]

    operations = [
        migrations.RunPython(create_superuser, migrations.RunPython.noop),
    ]
