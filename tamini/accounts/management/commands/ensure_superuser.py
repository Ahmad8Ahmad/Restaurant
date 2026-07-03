from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates or updates the superuser'

    def handle(self, *args, **options):
        email = 'ahmad19.8722.2@gmail.com'
        password = 'admin123'
        username = 'admin'

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'is_staff': True,
                'is_superuser': True,
            }
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser "{email}" created'))
        else:
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser "{email}" updated'))
