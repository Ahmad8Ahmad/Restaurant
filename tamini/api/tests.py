from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, FCMDevice
from restaurants.models import Restaurant, MenuItem, Category


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    },
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class StaffAccountApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@test.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Test Restaurant', is_approved=True,
        )
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def test_owner_can_create_staff_account(self):
        self._login(self.owner)
        resp = self.client.post('/api/auth/staff/', {
            'email': 'staff@test.com',
            'first_name': 'Kitchen',
            'phone': '0999',
            'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        staff = User.objects.get(email='staff@test.com')
        self.assertEqual(staff.role, 'staff')
        self.assertEqual(staff.restaurant_id, self.restaurant.id)
        self.assertTrue(staff.is_active)
        self.assertTrue(staff.is_verified)

    def test_owner_lists_only_own_staff(self):
        other = Restaurant.objects.create(owner=self.owner, name='Other')
        User.objects.create_user(
            email='a@test.com', username='a', password='x', role='staff',
            restaurant=other,
        )
        self._login(self.owner)
        resp = self.client.get('/api/auth/staff/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u['email'] for u in resp.data], [])

    def test_customer_cannot_create_staff(self):
        customer = User.objects.create_user(
            email='c@test.com', username='c', password='x', role='customer',
        )
        self._login(customer)
        resp = self.client.post('/api/auth/staff/', {
            'email': 'x@test.com', 'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_login(self):
        staff = User.objects.create_user(
            email='s@test.com', username='s', password='pass12345',
            role='staff', restaurant=self.restaurant, is_active=True,
            is_verified=True,
        )
        resp = self.client.post('/api/auth/login/', {
            'email': staff.email, 'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['user']['role'], 'staff')

    def test_staff_orders_scoped_to_their_restaurant(self):
        from orders.models import Order, OrderItem
        from restaurants.models import MenuItem, Category

        other = Restaurant.objects.create(owner=self.owner, name='Other')
        cat = Category.objects.create(name='Food')
        mi = MenuItem.objects.create(category=cat, restaurant=self.restaurant, name='Kebab', price=1000)
        mi2 = MenuItem.objects.create(category=cat, restaurant=other, name='Falafel', price=1000)
        o1 = Order.objects.create(restaurant=self.restaurant, delivery_address='A', total_price=1000, status='Pending')
        o2 = Order.objects.create(restaurant=other, delivery_address='B', total_price=1000, status='Pending')
        OrderItem.objects.create(order=o1, menu_item=mi, quantity=1, price=1000)
        OrderItem.objects.create(order=o2, menu_item=mi2, quantity=1, price=1000)

        staff = User.objects.create_user(
            email='s@test.com', username='s', password='x',
            role='staff', restaurant=self.restaurant,
        )
        self._login(staff)
        resp = self.client.get('/api/orders/')
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data['results']]
        self.assertIn(o1.id, ids)
        self.assertNotIn(o2.id, ids)

    def test_staff_can_update_order_status(self):
        from orders.models import Order, OrderItem
        from restaurants.models import MenuItem, Category

        cat = Category.objects.create(name='Food')
        mi = MenuItem.objects.create(category=cat, restaurant=self.restaurant, name='Kebab', price=1000)
        o = Order.objects.create(restaurant=self.restaurant, delivery_address='A', total_price=1000, status='Pending')
        OrderItem.objects.create(order=o, menu_item=mi, quantity=1, price=1000)

        staff = User.objects.create_user(
            email='s@test.com', username='s', password='x',
            role='staff', restaurant=self.restaurant,
        )
        self._login(staff)
        resp = self.client.patch(f'/api/orders/{o.id}/update-status/', {'status': 'Confirmed'})
        self.assertEqual(resp.status_code, 200, resp.content)
        o.refresh_from_db()
        self.assertEqual(o.status, 'Confirmed')


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    },
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class FcmAndDeliverySettingsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@test.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.restaurant = Restaurant.objects.create(owner=self.owner, name='R', is_approved=True)
        self.client = APIClient()

    def test_register_fcm_token(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/auth/fcm-token/', {'token': 'tok123', 'platform': 'android'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(FCMDevice.objects.filter(user=self.owner, token='tok123').exists())

    def test_register_fcm_token_requires_auth(self):
        resp = self.client.post('/api/auth/fcm-token/', {'token': 'tok123'})
        self.assertEqual(resp.status_code, 401)

    def test_delivery_settings_patch(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(f'/api/restaurants/{self.restaurant.id}/', {
            'delivery_fee': 3000,
            'delivery_fee_per_km': 500,
            'min_order_amount': 10000,
            'delivery_radius_km': 5,
            'has_own_delivery': True,
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.restaurant.refresh_from_db()
        self.assertEqual(float(self.restaurant.delivery_fee), 3000)
        self.assertEqual(float(self.restaurant.min_order_amount), 10000)

    def test_fcm_send_is_noop_without_credentials(self):
        from api import fcm

        sent = fcm.send_to_user(self.owner, 't', 'b')
        self.assertEqual(sent, 0)


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    },
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class MultiRestaurantApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@test.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.r1 = Restaurant.objects.create(owner=self.owner, name='R1', is_approved=True)
        self.r2 = Restaurant.objects.create(owner=self.owner, name='R2', is_approved=True)
        self.other_owner = User.objects.create_user(
            email='other@test.com', username='other', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.theirs = Restaurant.objects.create(owner=self.other_owner, name='Theirs', is_approved=True)
        self.cat = Category.objects.create(name='Food')
        self.client = APIClient()

    def test_my_returns_all_owned_restaurants(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get('/api/restaurants/my/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sorted(r['id'] for r in resp.data), sorted([self.r1.id, self.r2.id]))

    def test_owner_can_create_a_second_restaurant(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/restaurants/', {'name': 'R3'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Restaurant.objects.filter(owner=self.owner).count(), 3)

    def test_menu_item_created_for_requested_restaurant(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/menu-items/', {
            'restaurant': self.r2.id, 'category': self.cat.id,
            'name': 'Kebab', 'price': 5000,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        item = MenuItem.objects.get(id=resp.data['id'])
        self.assertEqual(item.restaurant_id, self.r2.id)

    def test_menu_item_created_without_restaurant_uses_first_owned(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/menu-items/', {
            'category': self.cat.id, 'name': 'Falafel', 'price': 3000,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        item = MenuItem.objects.get(id=resp.data['id'])
        self.assertEqual(item.restaurant_id, self.r1.id)

    def test_menu_item_create_rejects_other_owners_restaurant(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/menu-items/', {
            'restaurant': self.theirs.id, 'category': self.cat.id,
            'name': 'Stolen', 'price': 100,
        }, format='json')
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(MenuItem.objects.filter(name='Stolen').exists())

    def test_owner_can_update_menu_item_of_second_restaurant(self):
        mi = MenuItem.objects.create(
            restaurant=self.r2, category=self.cat, name='Kebab', price=5000,
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(f'/api/menu-items/{mi.id}/', {'price': 6000}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        mi.refresh_from_db()
        self.assertEqual(mi.price, 6000)

    def test_owner_cannot_update_another_owners_menu_item(self):
        mi = MenuItem.objects.create(
            restaurant=self.theirs, category=self.cat, name='Secret', price=5000,
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(f'/api/menu-items/{mi.id}/', {'price': 1}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_orders_filtered_per_restaurant(self):
        from orders.models import Order

        o1 = Order.objects.create(restaurant=self.r1, delivery_address='A', total_price=1000, status='Pending')
        o2 = Order.objects.create(restaurant=self.r2, delivery_address='B', total_price=1000, status='Pending')
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(f'/api/orders/?restaurant={self.r2.id}')
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data['results']]
        self.assertIn(o2.id, ids)
        self.assertNotIn(o1.id, ids)

    def test_staff_created_for_selected_restaurant(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/auth/staff/', {
            'restaurant_id': self.r2.id,
            'email': 'staff2@test.com',
            'first_name': 'Kitchen',
            'phone': '0999',
            'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        staff = User.objects.get(email='staff2@test.com')
        self.assertEqual(staff.restaurant_id, self.r2.id)

    def test_staff_listed_per_restaurant(self):
        User.objects.create_user(
            email='a@test.com', username='a', password='x',
            role='staff', restaurant=self.r2,
        )
        User.objects.create_user(
            email='b@test.com', username='b', password='x',
            role='staff', restaurant=self.r1,
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(f'/api/auth/staff/?restaurant={self.r2.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u['email'] for u in resp.data], ['a@test.com'])
