import pytest
from django.test import Client
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal

from accounts.models import User
from restaurants.models import Restaurant, MenuItem, Category
from delivery.models import DriverProfile, Delivery
from orders.models import Order, OrderItem
from payments.models import Payment, Commission


pytestmark = [
    pytest.mark.django_db,
]


@pytest.fixture(autouse=True)
def _test_settings(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }


@pytest.fixture
def site_settings():
    from support.models import SiteSettings
    s, _ = SiteSettings.objects.get_or_create(pk=1)
    s.commission_rate = 12
    s.delivery_base_fee = 200
    s.delivery_per_km_fee = 1500
    s.save()
    return s


class TestHundredOrderFlow:

    @pytest.fixture(autouse=True)
    def _setup(self, db, site_settings):
        self.customers = []
        self.restaurant_owners = []
        self.restaurants = []
        self.menu_items = []
        self.drivers = []
        self.orders = []
        self.payments = []
        self.deliveries = []

    def _create_customer(self, i):
        u = User.objects.create(
            email=f'customer{i:03d}@test.com',
            username=f'customer{i:03d}',
            role='customer',
            is_verified=True,
            is_approved=True,
        )
        return u

    def _create_restaurant_owner(self, i):
        u = User.objects.create(
            email=f'owner{i:03d}@test.com',
            username=f'owner{i:03d}',
            role='restaurant',
            is_verified=True,
            is_approved=True,
        )
        return u

    def _create_delivery_driver(self, i):
        u = User.objects.create(
            email=f'driver{i:03d}@test.com',
            username=f'driver{i:03d}',
            role='delivery',
            is_verified=True,
            is_approved=True,
        )
        DriverProfile.objects.create(user=u, is_approved=True)
        return u

    def _create_restaurant(self, owner, i):
        r = Restaurant.objects.create(
            owner=owner,
            name=f'Test Restaurant {i:03d}',
            description=f'Description for restaurant {i:03d}',
            address=f'Address {i:03d}',
            latitude=33.5 + (i * 0.001),
            longitude=36.27 + (i * 0.001),
            is_active=True,
            is_approved=True,
        )
        return r

    def _create_menu_item(self, restaurant):
        cat, _ = Category.objects.get_or_create(name=f'Category {restaurant.id}')
        item = MenuItem.objects.create(
            category=cat,
            restaurant=restaurant,
            name=f'Item {restaurant.id}',
            price=Decimal('5000.00'),
            is_available=True,
        )
        return item

    def _verify_order_complete(self, order):
        order.refresh_from_db()
        assert hasattr(order, 'payment'), f"Order {order.id} missing payment"
        assert order.payment.status == 'Completed', f"Order {order.id} payment not completed"
        assert hasattr(order, 'delivery'), f"Order {order.id} missing delivery"
        assert order.delivery.status == 'delivered', f"Order {order.id} delivery not delivered"
        assert order.status == 'Delivered', f"Order {order.id} status is {order.status}"

        commission = Commission.objects.filter(order=order, commission_type='restaurant').first()
        assert commission is not None, f"Order {order.id} missing restaurant commission"
        assert commission.amount > 0, f"Order {order.id} restaurant commission is 0"

        delivery_commission = Commission.objects.filter(
            delivery=order.delivery,
            commission_type='delivery'
        ).first()
        assert delivery_commission is not None, f"Order {order.id} missing delivery commission"
        assert delivery_commission.amount > 0, f"Order {order.id} delivery commission is 0"

    def test_direct_orm_flow_100_orders(self):
        n = 100

        for i in range(n):
            self.customers.append(self._create_customer(i))
            owner = self._create_restaurant_owner(i)
            self.restaurant_owners.append(owner)
            r = self._create_restaurant(owner, i)
            self.restaurants.append(r)
            item = self._create_menu_item(r)
            self.menu_items.append(item)
            self.drivers.append(self._create_delivery_driver(i))

        for i in range(n):
            customer = self.customers[i]
            restaurant = self.restaurants[i]
            menu_item = self.menu_items[i]
            driver = self.drivers[i]

            order = Order.objects.create(
                customer=customer,
                customer_name=customer.username,
                customer_phone=f'09{i:08d}',
                customer_email=customer.email,
                restaurant=restaurant,
                delivery_address=f'Delivery Address {i}',
                delivery_lat=33.51 + (i * 0.001),
                delivery_lng=36.28 + (i * 0.001),
                delivery_fee=Decimal('2000.00'),
                total_price=Decimal('7200.00'),
                status='Pending',
                customer_order_number=i + 1,
            )

            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=1,
                price=menu_item.price,
            )

            Payment.objects.create(
                order=order,
                amount=order.total_price,
                status='Completed',
                payment_method='Cash',
            )

            order.status = 'Out'
            order.save(update_fields=['status'])

            delivery = Delivery.objects.create(
                order=order,
                delivery_person=driver,
                status='delivered',
                current_lat=33.51 + (i * 0.001),
                current_lng=36.28 + (i * 0.001),
            )

            self.orders.append(order)
            self.payments.append(order.payment)
            self.deliveries.append(delivery)

        assert Order.objects.count() == n
        assert Payment.objects.count() == n
        assert Delivery.objects.count() == n
        assert Commission.objects.count() == n * 2

        for order in self.orders:
            self._verify_order_complete(order)

        completed = Order.objects.filter(status='Delivered').count()
        assert completed == n, f"Expected {n} delivered orders, got {completed}"

    def test_full_flow_via_test_client_with_session(self):
        n = 10

        for i in range(n):
            self.customers.append(self._create_customer(i))
            owner = self._create_restaurant_owner(i)
            self.restaurant_owners.append(owner)
            r = self._create_restaurant(owner, i)
            self.restaurants.append(r)
            item = self._create_menu_item(r)
            self.menu_items.append(item)
            self.drivers.append(self._create_delivery_driver(i))

        for i in range(n):
            customer = self.customers[i]
            restaurant = self.restaurants[i]
            menu_item = self.menu_items[i]
            restaurant_owner = self.restaurant_owners[i]
            driver = self.drivers[i]

            c = Client()
            session = c.session

            session['cart'] = {
                str(menu_item.id): {
                    'name': menu_item.name,
                    'price': float(menu_item.price),
                    'quantity': 1,
                    'restaurant_id': restaurant.id,
                }
            }
            session['cart_count'] = 1
            session['customer_lat'] = 33.51
            session['customer_lng'] = 36.28
            session.save()

            checkout_url = reverse('orders:checkout')
            response = c.post(checkout_url, {
                'delivery_address': f'Test Address {i}',
                'customer_name': customer.username,
                'customer_phone': f'09{i:08d}',
                'customer_email': customer.email,
                'delivery_lat': '33.51',
                'delivery_lng': '36.28',
            })
            assert response.status_code in (200, 302), f"Checkout failed for order {i}: {response.status_code}"

            order_id = c.session.get('placed_order_id')
            assert order_id is not None, f"No order ID in session for order {i}"
            order = Order.objects.get(id=order_id)
            self.orders.append(order)

            Payment.objects.create(
                order=order,
                amount=order.total_price,
                status='Completed',
                payment_method='Cash',
            )

            assert c.login(email=restaurant_owner.email, password=None) is False

            order.status = 'Out'
            order.save(update_fields=['status'])

            assert c.login(email=driver.email, password=None) is False

            delivery = Delivery.objects.create(
                order=order,
                delivery_person=driver,
                status='delivered',
                current_lat=33.51,
                current_lng=36.28,
            )
            self.deliveries.append(delivery)

        assert Order.objects.count() == n
        assert Payment.objects.count() == n
        assert Delivery.objects.count() == n

        for order in self.orders:
            self._verify_order_complete(order)

        completed = Order.objects.filter(status='Delivered').count()
        assert completed == n, f"Expected {n} delivered orders, got {completed}"

    def test_unique_order_numbers_per_customer(self):
        n = 5
        customers = [self._create_customer(i) for i in range(n)]
        owner = self._create_restaurant_owner(0)
        restaurant = self._create_restaurant(owner, 0)
        menu_item = self._create_menu_item(restaurant)
        driver = self._create_delivery_driver(0)

        for customer in customers:
            order = Order(
                customer=customer,
                restaurant=restaurant,
                delivery_address=f'Addr for {customer.id}',
                total_price=Decimal('5000.00'),
                status='Pending',
            )
            order_number = Order.objects.filter(customer=customer).count() + 1
            order.customer_order_number = order_number
            order.save()

            OrderItem.objects.create(
                order=order, menu_item=menu_item, quantity=1, price=menu_item.price,
            )

            Payment.objects.create(
                order=order, amount=order.total_price,
                status='Completed', payment_method='Cash',
            )
            order.status = 'Out'
            order.save(update_fields=['status'])

            Delivery.objects.create(
                order=order, delivery_person=driver, status='delivered',
            )

        for customer in customers:
            customer_orders = Order.objects.filter(customer=customer).order_by('customer_order_number')
            assert customer_orders.count() == 1
            assert customer_orders[0].customer_order_number == 1

        assert Order.objects.count() == n
        assert Commission.objects.filter(commission_type='restaurant').count() == n
        assert Commission.objects.filter(commission_type='delivery').count() == n

    def test_concurrent_order_creation(self):
        n = 100

        for i in range(n):
            self.customers.append(self._create_customer(i))
            owner = self._create_restaurant_owner(i)
            self.restaurant_owners.append(owner)
            r = self._create_restaurant(owner, i)
            self.restaurants.append(r)
            item = self._create_menu_item(r)
            self.menu_items.append(item)
            self.drivers.append(self._create_delivery_driver(i))

        for i in range(n):
            customer = self.customers[i]
            restaurant = self.restaurants[i]
            menu_item = self.menu_items[i]
            driver = self.drivers[i]

            order = Order.objects.create(
                customer=customer,
                restaurant=restaurant,
                delivery_address=f'Concurrent Address {i}',
                delivery_lat=33.51,
                delivery_lng=36.28,
                total_price=Decimal('7000.00'),
                status='Pending',
            )

            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=1,
                price=menu_item.price,
            )

            Payment.objects.create(
                order=order,
                amount=order.total_price,
                status='Completed',
                payment_method='Cash',
            )

            order.status = 'Out'
            order.save(update_fields=['status'])

            Delivery.objects.create(
                order=order,
                delivery_person=driver,
                status='delivered',
                current_lat=33.51,
                current_lng=36.28,
            )

        assert Order.objects.count() == n
        assert Payment.objects.count() == n
        assert Commission.objects.filter(commission_type='restaurant').count() == n
        assert Commission.objects.filter(commission_type='delivery').count() == n

        delivered = Order.objects.filter(status='Delivered').count()
        assert delivered == n

    def test_data_integrity_constraints(self):
        n = 100

        for i in range(n):
            self.customers.append(self._create_customer(i))
            owner = self._create_restaurant_owner(i)
            self.restaurant_owners.append(owner)
            r = self._create_restaurant(owner, i)
            self.restaurants.append(r)
            item = self._create_menu_item(r)
            self.menu_items.append(item)
            self.drivers.append(self._create_delivery_driver(i))

        for i in range(n):
            order = Order.objects.create(
                customer=self.customers[i],
                restaurant=self.restaurants[i],
                delivery_address=f'Address {i}',
                delivery_lat=33.51,
                delivery_lng=36.28,
                delivery_fee=Decimal('2000.00'),
                total_price=Decimal('7200.00'),
                status='Pending',
                customer_order_number=i + 1,
            )
            OrderItem.objects.create(
                order=order,
                menu_item=self.menu_items[i],
                quantity=1,
                price=self.menu_items[i].price,
            )
            Payment.objects.create(
                order=order,
                amount=order.total_price,
                status='Completed',
                payment_method='Cash',
            )
            order.status = 'Out'
            order.save(update_fields=['status'])
            Delivery.objects.create(
                order=order,
                delivery_person=self.drivers[i],
                status='delivered',
            )

            order.refresh_from_db()
            assert order.payment.status == 'Completed'
            assert order.delivery.status == 'delivered'
            assert order.status == 'Delivered'

            assert OrderItem.objects.filter(order=order).count() == 1
            assert Commission.objects.filter(commission_type='restaurant', order=order).exists()

        all_orders = Order.objects.all()
        order_ids = [o.id for o in all_orders]
        assert len(order_ids) == len(set(order_ids)), "Duplicate order IDs found"

        all_payments = Payment.objects.all()
        payment_order_ids = [p.order_id for p in all_payments]
        assert len(payment_order_ids) == len(set(payment_order_ids)), "Duplicate payments found"

        all_deliveries = Delivery.objects.all()
        delivery_order_ids = [d.order_id for d in all_deliveries]
        assert len(delivery_order_ids) == len(set(delivery_order_ids)), "Duplicate deliveries found"
