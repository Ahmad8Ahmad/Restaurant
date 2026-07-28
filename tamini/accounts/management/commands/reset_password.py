from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Reset a user password'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str)
        parser.add_argument('password', type=str)

    def handle(self, *args, **options):
        email = options['email']
        password = options['password']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {email} not found'))
            return
        user.set_password(password)
        user.is_active = True
        user.is_verified = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Password reset for {email}. Verified: True'))
