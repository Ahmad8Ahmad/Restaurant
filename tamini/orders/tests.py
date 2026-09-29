from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from orders import pricing
from orders.models import Cart, CartItem, Order, OUT_FOR_DELIVERY
from restaurants.models import Category, MenuItem, Restaurant
from support.models import SiteSettings


class _FakeSession:
    def __init__(self, key=None):
        self._key = key

    @property
    def session_key(self):
        return self._key

    def save(self):
        if not self._key:
            self._key = 'generated-session-key'


class CartGetForRequestTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cart-test', password='pass1234',
        )
        self.restaurant = Restaurant.objects.create(name='R')
        self.category = Category.objects.create(name='Cat')
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='M', price=100,
        )

    def _authed_request(self):
        req = RequestFactory().get('/')
        req.user = self.user
        return req

    def _guest_request(self, session_key='guest-session'):
        req = RequestFactory().get('/')
        req.user = AnonymousUser()
        req.session = _FakeSession(session_key)
        return req

    def test_authenticated_reuses_single_cart(self):
        c1 = Cart.get_for_request(self._authed_request())
        c2 = Cart.get_for_request(self._authed_request())
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)

    def test_guest_cart_keyed_by_session(self):
        cart = Cart.get_for_request(self._guest_request('k1'))
        self.assertIsNone(cart.user)
        self.assertEqual(cart.session_key, 'k1')
        other = Cart.get_for_request(self._guest_request('k2'))
        self.assertNotEqual(cart.pk, other.pk)

    def test_guest_session_is_saved_when_missing(self):
        req = self._guest_request(session_key=None)
        Cart.get_for_request(req)
        self.assertTrue(req.session.session_key)

    def test_view_cart_page_creates_one_cart_for_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('orders:view_cart'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)


class CartDuplicateCollapseTests(TransactionTestCase):
    """Dropping/re-adding the partial unique indexes requires schema DDL, which
    SQLite refuses inside a TestCase's wrapping transaction — hence
    TransactionTestCase."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cart-dup', password='pass1234',
        )
        self.restaurant = Restaurant.objects.create(name='R')
        self.category = Category.objects.create(name='Cat')
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='M', price=100,
        )

    def _authed_request(self):
        req = RequestFactory().get('/')
        req.user = self.user
        return req

    def test_duplicate_carts_collapsed(self):
        constraints = list(Cart._meta.constraints)
        with connection.schema_editor() as editor:
            for constraint in constraints:
                editor.remove_constraint(Cart, constraint)
        try:
            keep = Cart.objects.create(user=self.user, session_key=None)
            dup = Cart.objects.create(user=self.user, session_key=None)
            CartItem.objects.create(cart=dup, menu_item=self.menu_item, quantity=2)
            cart = Cart.get_for_request(self._authed_request())
            self.assertEqual(cart.pk, keep.pk)
            item = cart.items.get()
            self.assertEqual(item.quantity, 2)
            self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)
        finally:
            with connection.schema_editor() as editor:
                for constraint in constraints:
                    editor.add_constraint(Cart, constraint)

class PricingTests(TestCase):
    """The web cart, web checkout, API checkout and driver earnings must all
    agree on what an order costs. They each used to recompute the fee
    independently, so the same basket priced differently per client."""

    def setUp(self):
        site = SiteSettings.objects.create(
            delivery_base_fee=200, delivery_per_km_fee=1000,
        )
        self.restaurant = Restaurant.objects.create(
            name='R', latitude=33.5138, longitude=36.2765,
        )
        # ~1.1km north of the restaurant.
        self.lat = 33.5238
        self.lng = 36.2765

    def test_delivery_fee_is_base_plus_distance(self):
        expected = 200 + (pricing.haversine_km(
            self.lat, self.lng,
            self.restaurant.latitude, self.restaurant.longitude,
        ) * 1000)
        self.assertAlmostEqual(
            pricing.delivery_fee(self.restaurant, self.lat, self.lng), expected,
            delta=0.5,
        )

    def test_missing_coords_fall_back_to_flat_fee(self):
        from django.conf import settings
        self.assertEqual(
            pricing.delivery_fee(self.restaurant, None, None),
            settings.DELIVERY_FEE,
        )

    def test_ungeocoded_restaurant_falls_back_to_flat_fee(self):
        from django.conf import settings
        bare = Restaurant.objects.create(name='NoGeo')
        self.assertEqual(
            pricing.delivery_fee(bare, self.lat, self.lng),
            settings.DELIVERY_FEE,
        )

    def test_service_fee_is_five_percent(self):
        self.assertEqual(pricing.service_fee(10000), 500)
        self.assertEqual(pricing.service_fee(3333), 166.65)

    def test_quote_breakdown_sums_to_total(self):
        q = pricing.quote(10000, self.restaurant, self.lat, self.lng)
        self.assertEqual(
            q['total'], q['subtotal'] + q['delivery_fee'] + q['service_fee'],
        )
        self.assertEqual(q['service_fee'], 500)

    def test_farther_delivery_costs_more(self):
        near = pricing.delivery_fee(self.restaurant, 33.5138, 36.2765)
        far = pricing.delivery_fee(self.restaurant, 33.6138, 36.2765)
        self.assertGreater(far, near)


class CheckoutPriceParityTests(TestCase):
    """A basket must cost the same whether ordered through the DRF API or the
    web checkout. The API used to charge a flat base fee with no distance
    component and no service fee at all."""

    def setUp(self):
        SiteSettings.objects.create(delivery_base_fee=200, delivery_per_km_fee=1000)
        self.user = get_user_model().objects.create_user(
            username='parity', password='pass1234', email='parity@example.com',
        )
        self.restaurant = Restaurant.objects.create(
            name='R', latitude=33.5138, longitude=36.2765, is_active=True,
        )
        self.category = Category.objects.create(name='Cat', restaurant=self.restaurant)
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='M', price=2000,
        )
        self.payload = {
            'restaurant_id': self.restaurant.pk,
            'delivery_address': 'Somewhere',
            'delivery_lat': 33.5238,
            'delivery_lng': 36.2765,
            'customer_phone': '+963900000000',
            'items': [{'menu_item_id': self.menu_item.pk, 'quantity': 2}],
        }

    def test_api_checkout_matches_pricing_quote(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.user)
        resp = client.post(
            '/api/orders/checkout/', self.payload, format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get(pk=resp.data['id'])
        expected = pricing.quote(4000, self.restaurant, 33.5238, 36.2765)
        self.assertEqual(float(order.delivery_fee), float(expected['delivery_fee']))
        self.assertEqual(float(order.total_price), float(expected['total']))

    def test_api_checkout_includes_service_fee(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.user)
        resp = client.post(
            '/api/orders/checkout/', self.payload, format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get(pk=resp.data['id'])
        # 4000 subtotal + 5% service fee. The old API total omitted both the
        # distance component and the service fee.
        self.assertGreater(float(order.total_price), 4000)


class OutForDeliveryStatusTests(TestCase):
    """mark_as_out used to write a bare 'Out', which is not a key in
    Order.STATUS_CHOICES -- so it rendered untranslated and the API rejected
    it. Every status a view writes must be a declared choice."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='owner', password='pass1234', email='owner@example.com',
            role='restaurant',
        )
        self.restaurant = Restaurant.objects.create(
            name='R', owner=self.owner, is_active=True,
        )
        self.category = Category.objects.create(name='Cat', restaurant=self.restaurant)
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant, name='M', price=1000,
        )

    def test_out_for_delivery_is_a_declared_choice(self):
        self.assertIn(OUT_FOR_DELIVERY, [s for s, _ in Order.STATUS_CHOICES])

    def test_mark_as_out_writes_a_declared_choice(self):
        order = Order.objects.create(
            customer=self.owner, customer_name='x', customer_phone='1',
            restaurant=self.restaurant, delivery_address='a',
            total_price=1000, status='Confirmed',
        )
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('orders:mark_as_out', args=[order.pk]))
        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, OUT_FOR_DELIVERY)
        self.assertIn(order.status, [s for s, _ in Order.STATUS_CHOICES])

    def test_marked_out_order_is_visible_to_drivers(self):
        order = Order.objects.create(
            customer=self.owner, customer_name='x', customer_phone='1',
            restaurant=self.restaurant, delivery_address='a',
            total_price=1000, status='Confirmed',
        )
        self.client.force_login(self.owner)
        self.client.post(reverse('orders:mark_as_out', args=[order.pk]))
        order.refresh_from_db()
        # The web available-orders board filters on this status.
        self.assertTrue(
            Order.objects.filter(
                pk=order.pk, status__in=[OUT_FOR_DELIVERY, 'Out'],
            ).exists()
        )
