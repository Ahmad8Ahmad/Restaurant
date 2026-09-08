"""
Management command: seed accounts + restaurants for the Playwright load test.

Creates (idempotently, namespaced to ``@loadtest.tamini``):

    * ``--count`` restaurant owners, each with an approved Restaurant,
      a Category and one MenuItem.
    * ``--count`` delivery drivers, each with an approved DriverProfile.
    * ``--count`` customers.
    * one admin (superuser) used by the test to inspect payments,
      deliveries and commissions via the API.

All accounts use the same password and low-iteration PBKDF2 hashing (fast,
but still a valid Django auth credential so JWT + web-session login both
work).

Usage:
    python manage.py seed_load_test_data --settings=tamini.settings.dev --count 100
    python manage.py seed_load_test_data --purge --count 100
"""
import base64
import hashlib
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from restaurants.models import Restaurant, Category, MenuItem
from delivery.models import DriverProfile

DOMAIN = 'loadtest.tamini'

# Default PBKDF2 iterations are ~870k → ~0.25 s per hash. That makes seeding
# 300 accounts sluggish, so we craft a structurally-valid pbkdf2_sha256 hash
# with a low iteration count. The running server's built-in
# PBKDF2PasswordHasher reads the iteration count from the hash itself, so
# check_password() and both login paths work normally — but hashing is ~1 ms.
PBKDF2_ITERATIONS = 1000


def fast_hash(password: str) -> str:
    salt = base64.b64encode(os.urandom(12)).decode('ascii')
    digest = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'),
        PBKDF2_ITERATIONS,
    )
    return ('pbkdf2_sha256$%d$%s$%s' % (
        PBKDF2_ITERATIONS,
        salt,
        base64.b64encode(digest).decode('ascii'),
    ))


def email_for(role, i):
    return f'{role}{i:03d}@{DOMAIN}'


def hosts_for(role, i):
    return {role: email_for(role, i)}


class Command(BaseCommand):
    help = 'Seed load-test accounts (restaurants/drivers/customers) + menu items'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--password', default='LoadTest@123')
        parser.add_argument(
            '--purge', action='store_true',
            help='Delete previously seeded load-test users first, then reseed.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options['count']
        password = options['password']

        if options['purge']:
            removed = User.objects.filter(email__endswith=f'@{DOMAIN}').delete()[0]
            self.stdout.write(f'Purged {removed} previously seeded load-test rows.')

        def base_user(role, i, first_name='', phone_prefix='091'):
            return User(
                username=f'lt_{role}_{i:03d}',
                email=email_for(role, i),
                password=fast_hash(password),
                first_name=first_name,
                role=role,
                phone=f'{phone_prefix}{i:07d}',
                is_active=True,
                is_verified=True,
                is_approved=True,
            )

        # Admin used for read-only verification via the API.
        admin, _ = User.objects.update_or_create(
            email=email_for('admin', 0),
            defaults={
                'username': 'lt_admin',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
                'is_verified': True,
                'is_approved': True,
            },
        )
        admin.password = fast_hash(password)
        admin.save(update_fields=['password'])

        customers = []
        owners = []
        drivers = []

        for i in range(count):
            cust = base_user('customer', i, first_name=f'LoadTest Customer {i}')
            customers.append(cust)

            owner = base_user('restaurant', i, first_name=f'LoadTest Owner {i}', phone_prefix='092')
            owners.append(owner)

            driver = base_user('delivery', i, first_name=f'LoadTest Driver {i}', phone_prefix='093')
            drivers.append(driver)

        User.objects.bulk_create(customers + owners + drivers, ignore_conflicts=False)

        for i, owner in enumerate(owners):
            restaurant, _ = Restaurant.objects.update_or_create(
                owner=owner,
                defaults={
                    'name': f'LoadTest Restaurant {i:03d}',
                    'description': f'Playwright load-test restaurant #{i}',
                    'address': f'Load Test Street {i}, Damascus',
                    'phone': f'011-{i:07d}',
                    'latitude': 33.5138 + (i * 0.0005),
                    'longitude': 36.2765 + (i * 0.0005),
                    'is_active': True,
                    'is_approved': True,
                    'is_trendy': False,
                    'delivery_fee': 0,
                    'delivery_fee_per_km': 1500,
                    'min_order_amount': 0,
                },
            )
            restaurant.save()
            category, _ = Category.objects.get_or_create(
                name=f'LoadTest Category {i:03d}',
                restaurant=restaurant,
            )
            MenuItem.objects.update_or_create(
                restaurant=restaurant,
                name=f'LoadTest Item {i:03d}',
                defaults={
                    'category': category,
                    'description': f'Menu item for restaurant #{i}',
                    'price': 5000,
                    'is_available': True,
                },
            )
        for driver in drivers:
            DriverProfile.objects.update_or_create(
                user=driver,
                defaults={'is_approved': True},
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nSeeded {count} restaurants, {count} drivers, {count} customers '
            f'(password: {password}).\n'
            f'  Restaurants:  restaurant000@{DOMAIN} … restaurant{i:03d}@{DOMAIN}\n'
            f'  Drivers:      delivery000@{DOMAIN} … delivery{i:03d}@{DOMAIN}\n'
            f'  Customers:    customer000@{DOMAIN} … customer{i:03d}@{DOMAIN}\n'
            f'  Admin:        admin000@{DOMAIN}\n'
        ))