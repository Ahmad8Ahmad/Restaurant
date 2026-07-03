from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates or updates the superuser'

    def handle(self, *args, **options):
        email = 'ahmad19.8722.2@gmail.com'
        password = 'admin123'
        username = 'admin'

        try:
            user = User.objects.get(email=email)
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser "{email}" updated'))
            return
        except User.DoesNotExist:
            pass

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                email=email,
                username=username,
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser "{email}" created'))
            return

        for i in range(1, 100):
            alt_username = f'{username}{i}'
            if not User.objects.filter(username=alt_username).exists():
                User.objects.create_superuser(
                    email=email,
                    username=alt_username,
                    password=password,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Superuser "{email}" created with username "{alt_username}"'
                    )
                )
                return

        self.stdout.write(self.style.ERROR('Could not create superuser'))
