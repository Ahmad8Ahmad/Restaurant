from django.core.management.base import BaseCommand
from accounts.models import User

class Command(BaseCommand):
    help = 'Create superuser for production'

    def handle(self, *args, **options):
        email = 'taminyfood@gmail.com'
        username = 'admin'
        password = 'admin123'

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'User with email {email} already exists'))
            return

        User.objects.create_superuser(
            email=email,
            username=username,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'Superuser {email} created successfully'))
