"""Regression tests for the app <-> backend integration fixes.

Covers the five contract gaps that made the Flutter app fail against the
deployed API:

A1  POST /api/auth/send-verification-email/  (endpoint did not exist)
A2  GET  /api/orders/<id>/tracking/         (endpoint did not exist)
A3  POST /api/deliveries/<id>/reject/       (endpoint did not exist)
A4  WebSocket JWT auth via ?token=           (sockets were always anonymous)
A5  checkout honours payment_method          (field ignored, no payment_url)
"""

from unittest.mock import patch
import datetime

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from orders.models import Order, OrderItem, OUT_FOR_DELIVERY
from payments.models import Payment
from restaurants.models import Restaurant, MenuItem, Category
from delivery.models import Delivery


CHANNEL_LAYER = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


@override_settings(
    CHANNEL_LAYERS=CHANNEL_LAYER,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    # This suite makes several requests from one IP; the 3/min limit on the
    # verification endpoint is covered by its own test below.
    RATELIMIT_ENABLE=False,
)
class AppIntegrationTestBase(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email='customer@test.com', username='customer', password='pass12345',
            role='customer', is_active=True, is_verified=True,
        )
        self.other_customer = User.objects.create_user(
            email='other@test.com', username='other', password='pass12345',
            role='customer', is_active=True, is_verified=True,
        )
        self.owner = User.objects.create_user(
            email='owner@test.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True,
        )
        self.driver = User.objects.create_user(
            email='driver@test.com', username='driver', password='pass12345',
            role='delivery', is_active=True, is_verified=True, phone='0999',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Test Restaurant', is_approved=True, is_active=True,
            latitude=36.2, longitude=37.1, delivery_fee=5,
        )
        self.category = Category.objects.create(
            restaurant=self.restaurant, name='Mains',
        )
        self.menu_item = MenuItem.objects.create(
            category=self.category, restaurant=self.restaurant,
            name='Burger', price=10, is_available=True,
        )
        self.client = APIClient()

    def make_order(self, customer=None, status='Pending', total=25):
        order = Order.objects.create(
            customer=customer or self.customer,
            customer_name='Customer', customer_phone='0999',
            customer_email='customer@test.com',
            restaurant=self.restaurant,
            delivery_address='Somewhere 1',
            delivery_lat=36.3, delivery_lng=37.2,
            delivery_fee=5, total_price=total, status=status,
        )
        OrderItem.objects.create(
            order=order, menu_item=self.menu_item, quantity=1, price=10,
        )
        return order


class SendVerificationEmailTests(AppIntegrationTestBase):
    """A1.

    The view imports ``firebase_admin.auth`` inside the method, so the patch
    target is the real module attribute.
    """

    LINK = 'https://example.test/verify?oob=abc'

    def test_missing_email_is_400(self):
        resp = self.client.post(
            '/api/auth/send-verification-email/', {}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    @patch('api.views.auth.initialize_firebase')
    @patch('firebase_admin.auth.generate_email_verification_link')
    def test_sends_link_through_email_backend(self, gen_link, init_fb):
        gen_link.return_value = self.LINK
        resp = self.client.post(
            '/api/auth/send-verification-email/',
            {'email': 'someone@example.com'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['someone@example.com'])
        self.assertIn(self.LINK, mail.outbox[0].body)

    @patch('api.views.auth.initialize_firebase')
    @patch('firebase_admin.auth.generate_email_verification_link')
    def test_unknown_address_is_indistinguishable_from_known(self, gen_link, init_fb):
        """An unregistered address must get the same 200 as a registered one."""
        from firebase_admin import auth as fb_auth
        gen_link.side_effect = fb_auth.UserNotFoundError('no such user')
        resp = self.client.post(
            '/api/auth/send-verification-email/',
            {'email': 'nobody@example.com'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['detail'], 'Verification email sent.')
        self.assertEqual(len(mail.outbox), 0)

    @patch('api.views.auth.initialize_firebase')
    @patch('firebase_admin.auth.generate_email_verification_link')
    def test_infrastructure_failure_is_retryable(self, gen_link, init_fb):
        gen_link.side_effect = RuntimeError('firebase unreachable')
        resp = self.client.post(
            '/api/auth/send-verification-email/',
            {'email': 'someone@example.com'}, format='json',
        )
        self.assertEqual(resp.status_code, 503, resp.content)

    @patch('api.views.auth.initialize_firebase')
    @patch('firebase_admin.auth.generate_email_verification_link')
    def test_is_unauthenticated_accessible(self, gen_link, init_fb):
        """The app calls this before the user is signed in."""
        gen_link.return_value = self.LINK
        resp = self.client.post(
            '/api/auth/send-verification-email/',
            {'email': 'a@b.com'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    RATELIMIT_ENABLE=True,
    RATELIMIT_CACHE='default',
)
class SendVerificationEmailRateLimitTests(TestCase):
    """A1: the endpoint sends mail unauthenticated, so it must be throttled."""

    @patch('api.views.auth.initialize_firebase')
    @patch('firebase_admin.auth.generate_email_verification_link')
    def test_repeated_calls_are_throttled(self, gen_link, init_fb):
        gen_link.return_value = 'https://example.test/v'
        client = APIClient()
        codes = []
        for i in range(5):
            resp = client.post(
                '/api/auth/send-verification-email/',
                {'email': f'user{i}@example.com'}, format='json',
            )
            codes.append(resp.status_code)
        # django-ratelimit blocks with 403 once the 3/m budget is spent.
        self.assertIn(403, codes, f'expected throttling, got {codes}')


class OrderTrackingTests(AppIntegrationTestBase):
    """A2."""

    def test_customer_sees_driver_position(self):
        order = self.make_order(status=OUT_FOR_DELIVERY)
        delivery = Delivery.objects.create(
            order=order, delivery_person=self.driver, status='on_way',
            current_lat=36.25, current_lng=37.15,
        )
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get(f'/api/orders/{order.id}/tracking/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['id'], order.id)
        self.assertEqual(resp.data['status'], OUT_FOR_DELIVERY)
        self.assertEqual(resp.data['current_lat'], delivery.current_lat)
        self.assertEqual(resp.data['current_lng'], delivery.current_lng)
        self.assertEqual(resp.data['restaurant_lat'], 36.2)
        self.assertEqual(resp.data['restaurant_lng'], 37.1)

    def test_null_coordinates_before_a_driver_is_assigned(self):
        """The app parses doubles, so these must be JSON null, not absent."""
        order = self.make_order(status='Pending')
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get(f'/api/orders/{order.id}/tracking/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.data['current_lat'])
        self.assertIsNone(resp.data['current_lng'])
        for key in ('driver_name', 'driver_phone'):
            self.assertIn(key, resp.data)

    def test_stranger_cannot_track_someone_elses_order(self):
        order = self.make_order()
        self.client.force_authenticate(user=self.other_customer)
        resp = self.client.get(f'/api/orders/{order.id}/tracking/')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_restaurant_owner_can_track(self):
        order = self.make_order()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(f'/api/orders/{order.id}/tracking/')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_requires_authentication(self):
        order = self.make_order()
        resp = self.client.get(f'/api/orders/{order.id}/tracking/')
        self.assertEqual(resp.status_code, 401, resp.status_code)


class DeliveryRejectTests(AppIntegrationTestBase):
    """A3."""

    def test_driver_rejects_and_delivery_returns_to_the_board(self):
        order = self.make_order(status=OUT_FOR_DELIVERY)
        delivery = Delivery.objects.create(
            order=order, delivery_person=self.driver, status='searching',
        )
        self.client.force_authenticate(user=self.driver)
        resp = self.client.post(f'/api/deliveries/{delivery.id}/reject/')
        self.assertEqual(resp.status_code, 200, resp.content)
        delivery.refresh_from_db()
        self.assertIsNone(delivery.delivery_person)
        self.assertEqual(delivery.status, 'searching')
        # The order itself is untouched.
        order.refresh_from_db()
        self.assertEqual(order.status, OUT_FOR_DELIVERY)

    def test_cannot_reject_a_delivery_owned_by_another_driver(self):
        other_driver = User.objects.create_user(
            email='driver2@test.com', username='driver2', password='pass12345',
            role='delivery', is_active=True, is_verified=True,
        )
        order = self.make_order(status=OUT_FOR_DELIVERY)
        delivery = Delivery.objects.create(
            order=order, delivery_person=other_driver, status='on_way',
        )
        self.client.force_authenticate(user=self.driver)
        resp = self.client.post(f'/api/deliveries/{delivery.id}/reject/')
        self.assertEqual(resp.status_code, 403, resp.content)
        delivery.refresh_from_db()
        self.assertEqual(delivery.delivery_person, other_driver)

    def test_cannot_reject_a_completed_delivery(self):
        order = self.make_order(status='Delivered')
        delivery = Delivery.objects.create(
            order=order, delivery_person=self.driver, status='delivered',
        )
        self.client.force_authenticate(user=self.driver)
        resp = self.client.post(f'/api/deliveries/{delivery.id}/reject/')
        self.assertEqual(resp.status_code, 400, resp.content)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'delivered')

    def test_non_driver_is_forbidden(self):
        order = self.make_order(status=OUT_FOR_DELIVERY)
        delivery = Delivery.objects.create(order=order, status='searching')
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post(f'/api/deliveries/{delivery.id}/reject/')
        self.assertEqual(resp.status_code, 403, resp.content)


class WebSocketJwtAuthTests(TestCase):
    """A4: the app's ?token= handshake must resolve to a real user."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ws@test.com', username='ws', password='pass12345',
            role='customer', is_active=True, is_verified=True,
        )

    def _token(self, user=None):
        return str(RefreshToken.for_user(user or self.user).access_token)

    @staticmethod
    async def _passthrough(scope, receive, send):
        return scope

    async def _resolve(self, query_string):
        """Run the middleware over a fake handshake and return the scope.

        ``AuthMiddlewareStack`` always seeds ``scope['user']`` with an
        AnonymousUser before this middleware runs, so the fake scope does the
        same -- that is exactly the state the fallback is built for.
        """
        from django.contrib.auth.models import AnonymousUser
        from tamini.ws_auth import WebSocketSessionAuthMiddleware

        middleware = WebSocketSessionAuthMiddleware(self._passthrough)
        return await middleware(
            {
                'type': 'websocket',
                'query_string': query_string,
                'user': AnonymousUser(),
            },
            None, None,
        )

    async def test_valid_token_resolves_the_user(self):
        scope = await self._resolve(f'token={self._token()}'.encode())
        self.assertIsNotNone(scope['user'])
        self.assertEqual(scope['user'].id, self.user.id)

    async def test_garbage_token_leaves_the_socket_anonymous(self):
        scope = await self._resolve(b'token=not-a-real-jwt')
        self.assertTrue(scope['user'].is_anonymous)

    async def test_expired_token_leaves_the_socket_anonymous(self):
        from channels.db import database_sync_to_async

        token = RefreshToken.for_user(self.user).access_token
        token.set_exp(lifetime=datetime.timedelta(seconds=-10))
        scope = await self._resolve(f'token={token}'.encode())
        self.assertTrue(scope['user'].is_anonymous)

    async def test_no_token_leaves_the_socket_anonymous(self):
        scope = await self._resolve(b'')
        self.assertTrue(scope['user'].is_anonymous)

    async def test_inactive_user_is_rejected(self):
        from channels.db import database_sync_to_async

        token = self._token()

        @database_sync_to_async
        def deactivate():
            User.objects.filter(pk=self.user.pk).update(is_active=False)

        await deactivate()
        scope = await self._resolve(f'token={token}'.encode())
        self.assertTrue(scope['user'].is_anonymous)


@override_settings(
    CHANNEL_LAYERS=CHANNEL_LAYER,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CheckoutPaymentTests(AppIntegrationTestBase):
    """A5."""

    def _payload(self, payment_method=None):
        payload = {
            'restaurant_id': self.restaurant.id,
            'delivery_address': 'Somewhere 1',
            'customer_name': 'Customer',
            'customer_phone': '0999',
            'customer_email': 'customer@test.com',
            'items': [{'menu_item_id': self.menu_item.id, 'quantity': 2}],
        }
        if payment_method is not None:
            payload['payment_method'] = payment_method
        return payload

    def test_cash_confirms_the_order_and_returns_no_url(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post(
            '/api/orders/checkout/', self._payload('Cash'), format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get(id=resp.data['id'])
        self.assertEqual(order.status, 'Confirmed')
        self.assertIsNone(resp.data['payment_url'])
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.method, 'cash')
        self.assertEqual(payment.status, 'Completed')

    def test_card_returns_a_stripe_payment_url(self):
        self.client.force_authenticate(user=self.customer)

        def fake_create(order, amount, currency):
            obj, _ = Payment.objects.update_or_create(
                order=order,
                defaults={
                    'amount': amount, 'method': 'stripe',
                    'payment_method': 'Card', 'status': 'Pending',
                },
            )
            # The provider exposes the Stripe Checkout URL as a transient
            # attribute rather than a model field.
            obj.redirect_url = 'https://checkout.stripe.test/session/abc'
            return obj

        with patch(
            'payments.providers.stripe_provider.StripeProvider.is_enabled',
            return_value=True,
        ), patch(
            'payments.providers.stripe_provider.StripeProvider.create_payment',
            side_effect=fake_create,
        ):
            resp = self.client.post(
                '/api/orders/checkout/', self._payload('Card'), format='json',
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(
            resp.data['payment_url'], 'https://checkout.stripe.test/session/abc',
        )
        order = Order.objects.get(id=resp.data['id'])
        # Card orders stay Pending until the webhook confirms payment.
        self.assertEqual(order.status, 'Pending')

    def test_unavailable_gateway_rejects_before_writing_an_order(self):
        """No orphaned order when the gateway is disabled."""
        self.client.force_authenticate(user=self.customer)
        with patch(
            'payments.providers.stripe_provider.StripeProvider.is_enabled',
            return_value=False,
        ):
            resp = self.client.post(
                '/api/orders/checkout/', self._payload('Card'), format='json',
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(Order.objects.count(), 0)

    def test_response_is_a_flat_order_object(self):
        """The app does Order.fromJson(response) and reads payment_url off it."""
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post(
            '/api/orders/checkout/', self._payload('Cash'), format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        for key in ('id', 'status', 'total_price', 'restaurant', 'items'):
            self.assertIn(key, resp.data)
        self.assertIn('payment_url', resp.data)

    def test_omitting_payment_method_keeps_legacy_behaviour(self):
        """Existing web/mobile callers that don't send it must not break."""
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post(
            '/api/orders/checkout/', self._payload(), format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get(id=resp.data['id'])
        self.assertEqual(order.status, 'Pending')
        self.assertIsNone(resp.data['payment_url'])
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_invalid_payment_method_is_rejected(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post(
            '/api/orders/checkout/', self._payload('Bitcoin'), format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(Order.objects.count(), 0)
