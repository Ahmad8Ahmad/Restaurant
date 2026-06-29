import time
import pytest
from decimal import Decimal
from itertools import islice

from accounts.models import User
from restaurants.models import Restaurant, MenuItem, Category
from delivery.models import DriverProfile, Delivery
from orders.models import Order, OrderItem
from payments.models import Payment, Commission

pytestmark = [pytest.mark.django_db]

BATCH_SIZE = 500


def batched(iterable, size):
    it = iter(iterable)
    return iter(lambda: list(islice(it, size)), [])


@pytest.fixture(autouse=True)
def _test_settings(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture
def site_settings():
    from support.models import SiteSettings
    s, _ = SiteSettings.objects.get_or_create(pk=1)
    s.commission_rate = 12
    s.delivery_base_fee = 200
    s.delivery_per_km_fee = 1500
    s.save()
    return s


class TestStress100k:

    def _bulk_create_users(self, role, start, count, batch_size=BATCH_SIZE):
        users = []
        for i in range(start, start + count):
            users.append(User(
                email=f'{role}{i:06d}@test.com',
                username=f'{role}{i:06d}',
                role=role,
                is_verified=True,
                is_approved=True,
                password='!',
            ))
            if len(users) >= batch_size:
                User.objects.bulk_create(users, ignore_conflicts=True)
                users = []
        if users:
            User.objects.bulk_create(users, ignore_conflicts=True)

    def _bulk_create_driver_profiles(self, driver_ids, batch_size=BATCH_SIZE):
        profiles = []
        for uid in driver_ids:
            profiles.append(DriverProfile(user_id=uid, is_approved=True))
            if len(profiles) >= batch_size:
                DriverProfile.objects.bulk_create(profiles, ignore_conflicts=True)
                profiles = []
        if profiles:
            DriverProfile.objects.bulk_create(profiles, ignore_conflicts=True)

    def test_stress_100k(self, site_settings):
        n = 100_000
        t_start = time.time()

        # Phase 1: Users
        t0 = time.time()
        self._bulk_create_users('customer', 0, n)
        self._bulk_create_users('owner', 0, n)
        self._bulk_create_users('driver', 0, n)
        t1 = time.time()
        print(f"\n  Users created ({3*n}) in {t1-t0:.1f}s")

        customers = list(User.objects.filter(role='customer').order_by('id').values_list('id', flat=True))
        owners = list(User.objects.filter(role='owner').order_by('id').values_list('id', flat=True))
        driver_ids = list(User.objects.filter(role='driver').order_by('id').values_list('id', flat=True))
        self._bulk_create_driver_profiles(driver_ids)
        t2 = time.time()
        print(f"  Driver profiles created in {t2-t1:.1f}s")

        # Phase 2: Restaurants & MenuItems
        cat, _ = Category.objects.get_or_create(name='Global')
        restaurant_batch = []
        for i, owner_id in enumerate(owners):
            restaurant_batch.append(Restaurant(
                owner_id=owner_id,
                name=f'Restaurant {i:06d}',
                latitude=33.5 + (i * 1e-5),
                longitude=36.27 + (i * 1e-5),
                is_active=True,
                is_approved=True,
            ))
            if len(restaurant_batch) >= 500:
                Restaurant.objects.bulk_create(restaurant_batch)
                restaurant_batch = []
        if restaurant_batch:
            Restaurant.objects.bulk_create(restaurant_batch)
        restaurant_ids = list(Restaurant.objects.order_by('id').values_list('id', flat=True))

        menu_batch = []
        for rid in restaurant_ids:
            menu_batch.append(MenuItem(
                category_id=cat.id,
                restaurant_id=rid,
                name=f'Item {rid}',
                price=Decimal('5000.00'),
                is_available=True,
            ))
            if len(menu_batch) >= 500:
                MenuItem.objects.bulk_create(menu_batch)
                menu_batch = []
        if menu_batch:
            MenuItem.objects.bulk_create(menu_batch)
        t3 = time.time()
        print(f"  Restaurants & MenuItems created in {t3-t2:.1f}s")

        restaurant_ids = list(Restaurant.objects.order_by('id').values_list('id', flat=True))
        menu_item_ids = list(MenuItem.objects.order_by('id').values_list('id', flat=True))

        # Phase 3: Orders
        order_batch = []
        for i, (cust_id, rest_id) in enumerate(zip(customers, restaurant_ids)):
            order_batch.append(Order(
                customer_id=cust_id,
                customer_name=f'customer{i:06d}',
                customer_phone=f'09{i%100000000:08d}',
                customer_email=f'customer{i:06d}@test.com',
                restaurant_id=rest_id,
                delivery_address=f'Address {i}',
                delivery_lat=33.51,
                delivery_lng=36.28,
                delivery_fee=Decimal('2000.00'),
                total_price=Decimal('7200.00'),
                status='Out',
                customer_order_number=i + 1,
            ))
            if len(order_batch) >= 500:
                Order.objects.bulk_create(order_batch)
                order_batch = []
        if order_batch:
            Order.objects.bulk_create(order_batch)
        t4 = time.time()
        print(f"  Orders created in {t4-t3:.1f}s")

        all_orders = list(Order.objects.order_by('id').values_list('id', flat=True))

        # Phase 4: OrderItems
        oi_batch = []
        for oid, mid in zip(all_orders, menu_item_ids):
            oi_batch.append(OrderItem(
                order_id=oid,
                menu_item_id=mid,
                quantity=1,
                price=Decimal('5000.00'),
            ))
            if len(oi_batch) >= 500:
                OrderItem.objects.bulk_create(oi_batch)
                oi_batch = []
        if oi_batch:
            OrderItem.objects.bulk_create(oi_batch)
        t5 = time.time()
        print(f"  OrderItems created in {t5-t4:.1f}s")

        # Phase 5: Payments
        pay_batch = []
        for oid in all_orders:
            pay_batch.append(Payment(
                order_id=oid,
                amount=Decimal('7200.00'),
                status='Completed',
                payment_method='Cash',
            ))
            if len(pay_batch) >= 500:
                Payment.objects.bulk_create(pay_batch)
                pay_batch = []
        if pay_batch:
            Payment.objects.bulk_create(pay_batch)
        t6 = time.time()
        print(f"  Payments created in {t6-t5:.1f}s")

        # Phase 6: Deliveries & commissions
        del_batch = []
        rest_comm_batch = []
        del_comm_batch = []
        for i, (oid, did) in enumerate(zip(all_orders, driver_ids)):
            del_batch.append(Delivery(
                order_id=oid,
                delivery_person_id=did,
                status='delivered',
                current_lat=33.51,
                current_lng=36.28,
            ))
            if len(del_batch) >= 500:
                deliveries = Delivery.objects.bulk_create(del_batch)
                for d in deliveries:
                    rest_comm_batch.append(Commission(
                        commission_type='restaurant',
                        order_id=d.order_id,
                        amount=Decimal('864.00'),
                    ))
                    del_comm_batch.append(Commission(
                        commission_type='delivery',
                        delivery_id=d.id,
                        amount=Decimal('240.00'),
                    ))
                if len(rest_comm_batch) >= 500:
                    Commission.objects.bulk_create(rest_comm_batch)
                    Commission.objects.bulk_create(del_comm_batch)
                    rest_comm_batch = []
                    del_comm_batch = []
                del_batch = []
        if del_batch:
            deliveries = Delivery.objects.bulk_create(del_batch)
            for d in deliveries:
                rest_comm_batch.append(Commission(
                    commission_type='restaurant',
                    order_id=d.order_id,
                    amount=Decimal('864.00'),
                ))
                del_comm_batch.append(Commission(
                    commission_type='delivery',
                    delivery_id=d.id,
                    amount=Decimal('240.00'),
                ))
        if rest_comm_batch:
            Commission.objects.bulk_create(rest_comm_batch)
            Commission.objects.bulk_create(del_comm_batch)
        t7 = time.time()
        print(f"  Deliveries & Commissions created in {t7-t6:.1f}s")

        # Phase 7: Update orders to Delivered
        for batch in batched(all_orders, 500):
            Order.objects.filter(id__in=batch).update(status='Delivered')
        t8 = time.time()
        print(f"  Order status updates in {t8-t7:.1f}s")

        t_total = time.time() - t_start
        print(f"\n  TOTAL TIME: {t_total:.1f}s")

        # Verification
        assert User.objects.count() == 3 * n
        assert DriverProfile.objects.count() == n
        assert Restaurant.objects.count() == n
        assert MenuItem.objects.count() == n
        assert Order.objects.count() == n
        assert OrderItem.objects.count() == n
        assert Payment.objects.count() == n
        assert Delivery.objects.count() == n
        assert Commission.objects.count() == 2 * n

        delivered = Order.objects.filter(status='Delivered').count()
        assert delivered == n

        completed_payments = Payment.objects.filter(status='Completed').count()
        assert completed_payments == n
