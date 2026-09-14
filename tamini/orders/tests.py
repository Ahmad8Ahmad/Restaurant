from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from orders.models import Cart, CartItem
from restaurants.models import Category, MenuItem, Restaurant


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