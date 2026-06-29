from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_is_approved'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='otp_code',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
