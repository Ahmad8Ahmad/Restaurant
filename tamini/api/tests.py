from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, FCMDevice
from orders.models import Order, OUT_FOR_DELIVERY, OUT_FOR_DELIVERY_STATUSES
from restaurants.models import Restaurant, MenuItem, Category, SiteContent
from user_settings.models import UserPreference


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

    def test_owner_can_close_restaurant_via_patch(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(f'/api/restaurants/{self.r1.id}/', {'is_active': False}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.r1.refresh_from_db()
        self.assertFalse(self.r1.is_active)

    def test_toggle_active_action(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(f'/api/restaurants/{self.r1.id}/toggle_active/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.data['is_active'])
        self.r1.refresh_from_db()
        self.assertFalse(self.r1.is_active)

    def test_toggle_active_on_foreign_restaurant_not_found(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(f'/api/restaurants/{self.theirs.id}/toggle_active/')
        self.assertEqual(resp.status_code, 404)

    def test_checkout_rejects_closed_restaurant(self):
        mi = MenuItem.objects.create(restaurant=self.r1, category=self.cat, name='Kebab', price=5000)
        self.r1.is_active = False
        self.r1.save(update_fields=['is_active'])
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/orders/checkout/', {
            'restaurant_id': self.r1.id,
            'delivery_address': 'Damascus',
            'items': [{'menu_item_id': mi.id, 'quantity': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('مغلق', resp.data['detail'])


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    },
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class CartApiTests(TestCase):
    """Regression tests for the Flutter cart API.

    `_get_cart` returns a single Cart object; these endpoints previously
    unpacked it as a (cart, created) tuple, raising
    `TypeError: cannot unpack non-iterable Cart object` on every request.
    """
    def setUp(self):
        self.customer = User.objects.create_user(
            email='customer@test.com', username='customer', password='pass12345',
            role='customer', is_active=True, is_verified=True,
        )
        self.owner = User.objects.create_user(
            email='owner@test.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Test Restaurant', is_approved=True,
        )
        self.category = Category.objects.create(name='Food')
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='Falafel', price=1000, is_available=True,
        )
        self.hidden = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='Hidden', price=500, is_available=False,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.customer)

    def test_add_item_creates_cart(self):
        resp = self.client.post('/api/cart/add/', {
            'menu_item_id': self.menu_item.id, 'quantity': 1,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['total_quantity'], 1)
        self.assertEqual(len(resp.data['items']), 1)

    def test_add_same_item_increments_quantity(self):
        self.client.post('/api/cart/add/', {
            'menu_item_id': self.menu_item.id, 'quantity': 2,
        }, format='json')
        resp = self.client.post('/api/cart/add/', {
            'menu_item_id': self.menu_item.id, 'quantity': 1,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['total_quantity'], 3)

    def test_add_unavailable_item_returns_404(self):
        resp = self.client.post('/api/cart/add/', {
            'menu_item_id': self.hidden.id, 'quantity': 1,
        }, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_cart_get_update_remove_clear(self):
        from orders.models import Cart

        add = self.client.post('/api/cart/add/', {
            'menu_item_id': self.menu_item.id, 'quantity': 1,
        }, format='json')
        item_id = add.data['items'][0]['id']

        get = self.client.get('/api/cart/')
        self.assertEqual(get.status_code, 200, get.content)
        self.assertEqual(get.data['total_quantity'], 1)

        upd = self.client.put(f'/api/cart/item/{item_id}/', {'quantity': 4}, format='json')
        self.assertEqual(upd.status_code, 200, upd.content)
        self.assertEqual(upd.data['total_quantity'], 4)

        rem = self.client.delete(f'/api/cart/item/{item_id}/remove/')
        self.assertEqual(rem.status_code, 200, rem.content)
        self.assertEqual(rem.data['items'], [])

        self.client.post('/api/cart/add/', {
            'menu_item_id': self.menu_item.id, 'quantity': 2,
        }, format='json')
        clear = self.client.delete('/api/cart/clear/')
        self.assertEqual(clear.status_code, 200, clear.content)
        cart = Cart.objects.get(user=self.customer, session_key__isnull=True)
        self.assertEqual(cart.items.count(), 0)


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    },
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class DriverAnnouncementApiTests(TestCase):
    """DeliveryViewSet.available only harvests orders whose status is an
    out-for-delivery one, so that transition -- not order creation -- is the
    moment drivers have to hear about. Order creation announces too early to
    ever resolve: the order is still Pending, so a driver who refreshes on that
    push correctly sees an empty board.

    Every status write path must announce the transition, and only once.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='announce-owner', password='pass1234',
            email='announce-owner@example.com', role='restaurant',
        )
        self.restaurant = Restaurant.objects.create(
            name='Announce R', owner=self.owner, is_active=True,
        )
        category = Category.objects.create(
            name='Announce Cat', restaurant=self.restaurant,
        )
        self.menu_item = MenuItem.objects.create(
            category=category, restaurant=self.restaurant,
            name='Announce M', price=1000,
        )
        self.order = Order.objects.create(
            customer=self.owner, customer_name='x', customer_phone='1',
            restaurant=self.restaurant, delivery_address='a',
            total_price=1000, status='Preparing',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

        layer = MagicMock()
        layer.group_send = AsyncMock()
        self.group_send = layer.group_send
        patcher = patch(
            'orders.notifications.get_channel_layer', return_value=layer,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _announcements(self):
        return [call.args for call in self.group_send.call_args_list]

    def _set_status(self, status, url=None):
        return self.client.patch(
            url or f'/api/orders/{self.order.pk}/update-status/',
            {'status': status}, format='json',
        )

    def test_transition_announces_the_driver_group(self):
        resp = self._set_status(OUT_FOR_DELIVERY)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OUT_FOR_DELIVERY)

        announcements = self._announcements()
        self.assertEqual(len(announcements), 1, announcements)
        group, payload = announcements[0]
        self.assertEqual(group, 'driver_notifications')
        self.assertEqual(payload['type'], 'new_order_available')
        self.assertEqual(payload['order_id'], self.order.pk)

    def test_announced_order_is_actually_harvestable_by_drivers(self):
        """Guards the two halves meeting: the status the announcement fires on
        has to be one DeliveryViewSet.available will pick up."""
        self._set_status(OUT_FOR_DELIVERY)
        self.assertTrue(
            Order.objects.filter(
                pk=self.order.pk, status__in=OUT_FOR_DELIVERY_STATUSES,
            ).exists()
        )

    def test_other_statuses_do_not_announce(self):
        resp = self._set_status('Confirmed')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.group_send.assert_not_called()

    def test_repeating_the_same_status_announces_once(self):
        url = f'/api/orders/{self.order.pk}/update-status/'
        self.assertEqual(self._set_status(OUT_FOR_DELIVERY, url).status_code, 200)
        self.assertEqual(self._set_status(OUT_FOR_DELIVERY, url).status_code, 200)
        self.assertEqual(len(self._announcements()), 1, self._announcements())

    def test_bare_detail_patch_announces_too(self):
        """The app used to PATCH the detail route directly, which is how the
        broadcast went missing in the first place. Keep it covered."""
        resp = self._set_status(OUT_FOR_DELIVERY, f'/api/orders/{self.order.pk}/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(self._announcements()), 1, self._announcements())

    def test_rejected_status_neither_writes_nor_announces(self):
        resp = self._set_status('Nonsense')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Preparing')
        self.group_send.assert_not_called()


@override_settings(
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    },
)
class SettingsApiTests(TestCase):
    """JSON counterparts of the session-authenticated /settings/ page."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='prefs@test.com', username='prefs', password='pass12345',
            role='customer', is_active=True, is_verified=True,
        )
        self.client = APIClient()

    # ── preferences ────────────────────────────────────────────────

    def test_preferences_require_authentication(self):
        resp = self.client.get('/api/settings/preferences/')
        self.assertIn(resp.status_code, (401, 403), resp.content)

    def test_preferences_get_creates_defaults(self):
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/settings/preferences/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['theme'], 'light')
        self.assertTrue(resp.data['notify_order_updates'])
        self.assertTrue(resp.data['notify_promotions'])
        self.assertTrue(resp.data['notify_email'])
        self.assertTrue(UserPreference.objects.filter(user=self.user).exists())

    def test_preferences_put_persists(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.put('/api/settings/preferences/', {
            'theme': 'dark',
            'notify_order_updates': True,
            'notify_promotions': False,
            'notify_email': True,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(pref.theme, 'dark')
        self.assertTrue(pref.notify_order_updates)
        self.assertFalse(pref.notify_promotions)
        self.assertTrue(pref.notify_email)

    def test_preferences_patch_is_partial(self):
        self.client.force_authenticate(user=self.user)
        self.client.put('/api/settings/preferences/', {
            'theme': 'system',
            'notify_order_updates': False,
            'notify_promotions': True,
            'notify_email': False,
        }, format='json')
        resp = self.client.patch('/api/settings/preferences/', {
            'notify_promotions': False,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(pref.theme, 'system')
        self.assertFalse(pref.notify_promotions)
        self.assertFalse(pref.notify_order_updates)

    def test_preferences_rejects_unknown_theme(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.put('/api/settings/preferences/', {'theme': 'neon'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    # ── legal ──────────────────────────────────────────────────────

    def test_legal_terms_default_arabic(self):
        content = SiteContent.load()
        content.terms_of_service_ar = '<p>الشروط</p>'
        content.terms_of_service_en = '<p>English terms</p>'
        content.save()
        resp = self.client.get('/api/legal/terms/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['slug'], 'terms')
        self.assertEqual(resp.data['title'], 'شروط الخدمة')
        self.assertEqual(resp.data['content'], '<p>الشروط</p>')

    def test_legal_privacy_honours_lang_param(self):
        content = SiteContent.load()
        content.privacy_policy_ar = '<p>عربي</p>'
        content.privacy_policy_en = '<p>English</p>'
        content.save()
        resp = self.client.get('/api/legal/privacy/?lang=en')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['title'], 'Privacy Policy')
        self.assertEqual(resp.data['content'], '<p>English</p>')

    def test_legal_falls_back_to_arabic_when_translation_missing(self):
        content = SiteContent.load()
        content.privacy_policy_ar = '<p>عربي فقط</p>'
        content.privacy_policy_en = ''
        content.save()
        resp = self.client.get('/api/legal/privacy/?lang=en')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['content'], '<p>عربي فقط</p>')

    def test_legal_unknown_slug_is_404(self):
        self.assertEqual(self.client.get('/api/legal/nope/').status_code, 404)

    # ── delete account ─────────────────────────────────────────────

    @patch('user_settings.services.delete_firebase_user')
    @patch('api.views.settings.services.verify_firebase_id_token')
    def test_delete_account_with_id_token(self, verify_id_token, delete_fb_user):
        self.user.firebase_uid = 'fb-uid-1'
        self.user.save(update_fields=['firebase_uid'])
        UserPreference.get_or_create_for_user(self.user)
        verify_id_token.return_value = {'uid': 'fb-uid-1', 'email': 'prefs@test.com'}

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/settings/delete-account/', {'id_token': 'tok'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data['ok'])
        delete_fb_user.assert_called_once_with('fb-uid-1')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(UserPreference.objects.filter(user_id=self.user.pk).exists())

    @patch('user_settings.services.delete_firebase_user')
    @patch('api.views.settings.services.verify_firebase_id_token')
    def test_delete_account_rejects_token_of_another_user(self, verify_id_token, delete_fb_user):
        self.user.firebase_uid = 'fb-uid-1'
        self.user.save(update_fields=['firebase_uid'])
        verify_id_token.return_value = {'uid': 'someone-else', 'email': 'x@test.com'}

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/settings/delete-account/', {'id_token': 'tok'}, format='json')

        self.assertEqual(resp.status_code, 403, resp.content)
        delete_fb_user.assert_not_called()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    @patch('user_settings.services.delete_firebase_user')
    @patch('api.views.settings.services.verify_firebase_password')
    def test_delete_account_with_password(self, verify_password, delete_fb_user):
        verify_password.return_value = 'fb-uid-2'

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/settings/delete-account/', {
            'email': 'prefs@test.com', 'password': 'pass12345',
        }, format='json')

        self.assertEqual(resp.status_code, 200, resp.content)
        verify_password.assert_called_once_with('prefs@test.com', 'pass12345')
        delete_fb_user.assert_called_once_with(None)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    @patch('api.views.settings.services.verify_firebase_password')
    def test_delete_account_rejects_wrong_password(self, verify_password):
        verify_password.return_value = None

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/settings/delete-account/', {
            'email': 'prefs@test.com', 'password': 'nope',
        }, format='json')

        self.assertEqual(resp.status_code, 401, resp.content)
        self.assertFalse(resp.data['ok'])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_account_requires_authentication(self):
        resp = self.client.post('/api/settings/delete-account/', {'id_token': 'tok'}, format='json')
        self.assertIn(resp.status_code, (401, 403), resp.content)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
