from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import User
from restaurants.models import Restaurant, Category, MenuItem
from delivery.models import DriverProfile
from orders.models import Order, OrderItem
from django.db import transaction
import random


class Command(BaseCommand):
    help = 'Seed test data for all roles'

    @transaction.atomic
    def handle(self, *args, **options):
        pw = 'Test@123'

        # Superuser
        su, _ = User.objects.get_or_create(email='admin@tamini.com', defaults={
            'username': 'admin', 'role': 'admin', 'is_staff': True,
            'is_superuser': True, 'is_active': True, 'is_verified': True, 'is_approved': True
        })
        su.set_password(pw)
        su.save()

        # Customer
        cust, _ = User.objects.get_or_create(email='customer@test.com', defaults={
            'username': 'customer_1', 'role': 'customer',
            'is_active': True, 'is_verified': True, 'is_approved': True
        })
        cust.set_password(pw)
        cust.save()

        # Restaurant owner
        rest_owner, _ = User.objects.get_or_create(email='restaurant@test.com', defaults={
            'username': 'restaurant_1', 'role': 'restaurant',
            'is_active': True, 'is_verified': True, 'is_approved': True
        })
        rest_owner.set_password(pw)
        rest_owner.save()

        # Delivery driver
        driver_user, _ = User.objects.get_or_create(email='delivery@test.com', defaults={
            'username': 'delivery_1', 'role': 'delivery',
            'is_active': True, 'is_verified': True, 'is_approved': True
        })
        driver_user.set_password(pw)
        driver_user.save()

        DriverProfile.objects.get_or_create(user=driver_user, defaults={'is_approved': True})

        # Restaurant
        restaurant, created = Restaurant.objects.get_or_create(
            owner=rest_owner,
            defaults={
                'name': 'مطعم طعميني', 'description': 'أشهر المأكولات الشرقية والغربية',
                'address': 'دمشق, سورية', 'phone': '011-1234567',
                'latitude': 33.5138, 'longitude': 36.2765,
                'is_active': True, 'is_approved': True, 'is_trendy': True
            }
        )

        # Categories & Menu Items
        cat1, _ = Category.objects.get_or_create(name='مشاوي', restaurant=restaurant)
        cat2, _ = Category.objects.get_or_create(name='مقبلات', restaurant=restaurant)

        items = [
            (cat1, 'شيش طاووق', 25000, 'صدور دجاج مشوية على الفحم'),
            (cat1, 'كباب', 30000, 'لحم مفروم مشوي'),
            (cat1, 'أضلاع', 45000, 'أضلاع لحم مشوية'),
            (cat1, 'اوصال', 35000, 'لحم خروف مشوي'),
            (cat1, 'ريش', 40000, 'ريش غنم مشوية'),
            (cat2, 'حمص', 8000, 'حمص بطحينة'),
            (cat2, 'متبل', 10000, 'باذنجان مشوي مع طحينة'),
            (cat2, 'تبولة', 7000, 'تبولة ناعمة'),
            (cat2, 'فتوش', 7000, 'سلطة خضار مع خبز مقلي'),
        ]

        for cat, name, price, desc in items:
            MenuItem.objects.get_or_create(
                category=cat, restaurant=restaurant, name=name,
                defaults={'price': price, 'description': desc, 'is_available': True}
            )

        # A sample order
        if not Order.objects.filter(customer=cust).exists():
            menu_items = list(restaurant.menu_items.all())
            if menu_items:
                order = Order.objects.create(
                    customer=cust, customer_name='عميل تجربة',
                    customer_phone='0933000000', customer_email=cust.email,
                    restaurant=restaurant,
                    delivery_address='دمشق, المزة, شارع 29 أيار',
                    delivery_lat=33.5100, delivery_lng=36.2700,
                    delivery_fee=5000, total_price=0,
                    status='Pending'
                )
                total = 0
                for _ in range(random.randint(1, 3)):
                    mi = random.choice(menu_items)
                    qty = random.randint(1, 2)
                    OrderItem.objects.create(
                        order=order, menu_item=mi,
                        quantity=qty, price=mi.price
                    )
                    total += mi.price * qty
                order.total_price = total + order.delivery_fee
                order.save()

        self.stdout.write(self.style.SUCCESS(
            f'\nTest users created (password: {pw}):\n'
            f'  Admin:      admin@tamini.com\n'
            f'  Customer:   customer@test.com\n'
            f'  Restaurant: restaurant@test.com\n'
            f'  Delivery:   delivery@test.com\n'
        ))
