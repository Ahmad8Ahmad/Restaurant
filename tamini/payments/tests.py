from unittest import mock

import json

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse

from accounts.models import User
from orders.models import Order
from payments import services
from payments.models import Payment
from payments.providers import enabled_providers, get_provider
from payments.providers.base import PaymentError
from restaurants.models import Restaurant
from support.models import SiteSettings


@pytest.fixture
def customer(db):
    return User.objects.create(email='cust@test.com', username='cust')


@pytest.fixture
def restaurant(db):
    owner = User.objects.create(email='own@test.com', username='own')
    return Restaurant.objects.create(
        name='Test', owner=owner, latitude=33.5, longitude=36.2,
    )


@pytest.fixture
def order(customer, restaurant):
    return Order.objects.create(
        customer=customer,
        restaurant=restaurant,
        delivery_address='Addr',
        total_price=10000,
        status='Pending',
    )


@pytest.fixture
def site_settings(db):
    cache.clear()
    return SiteSettings.objects.create(
        stripe_publishable_key='pk_test_x',
        stripe_secret_key='sk_test_x',
        stripe_webhook_secret='whsec_test',
        stripe_mode='enabled',
        stripe_exchange_rate=13000,
        stripe_currency='usd',
    )


@pytest.mark.django_db
class TestPaymentProviders:

    def test_cash_creates_payment_and_confirms_order(self, order):
        payment = services.initiate_payment(order, 'cash')
        assert payment.method == 'cash'
        assert payment.payment_method == 'Cash'
        assert payment.status == 'Completed'
        order.refresh_from_db()
        assert order.status == 'Confirmed'

    def test_disabled_stripe_is_enabled_false_and_hidden(self, order, db):
        SiteSettings.objects.create(
            stripe_publishable_key='pk_test_x',
            stripe_secret_key='sk_test_x',
            stripe_mode='disabled',
        )
        provider = get_provider('stripe')
        assert provider.is_enabled() is False
        providers = enabled_providers()
        assert all(p.value != 'stripe' for p in providers)
        assert any(p.value == 'cash' for p in providers)
        with pytest.raises(PaymentError):
            services.initiate_payment(order, 'stripe')
        assert Payment.objects.filter(order=order).count() == 0

    def test_webhook_bad_signature_returns_400_and_order_unchanged(self, order, client, site_settings):
        from django.urls import reverse
        url = reverse('stripe_webhook')
        resp = client.post(url, data=b'{}', content_type='application/json', HTTP_STRIPE_SIGNATURE='bad')
        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.status == 'Pending'

    def test_stripe_snapshots_exchange_rate(self, order, site_settings):
        req = RequestFactory().post('/')
        session_mock = mock.MagicMock()
        session_mock.id = 'cs_test_123'
        session_mock.url = 'https://checkout.stripe.com/pay/cs_test_123'
        with mock.patch('payments.providers.stripe_provider.stripe.checkout.Session.create', return_value=session_mock):
            payment = services.initiate_payment(order, 'stripe', request=req)
        payment.refresh_from_db()
        assert payment.exchange_rate == 13000
        assert payment.method == 'stripe'
        assert payment.provider_ref == 'cs_test_123'

    def test_stripe_api_mocked_no_real_network(self, order, site_settings):
        req = RequestFactory().post('/')
        req.user = mock.MagicMock(is_authenticated=True, email='a@b.com')
        session_mock = mock.MagicMock()
        session_mock.id = 'cs_test_net'
        session_mock.url = 'https://checkout.stripe.com/pay/cs_test_net'
        with mock.patch('payments.providers.stripe_provider.stripe.checkout.Session.create', return_value=session_mock) as mocked:
            payment = services.initiate_payment(order, 'stripe', request=req)
        mocked.assert_called_once()
        assert payment.transaction_id == 'cs_test_net'
        assert order.status == 'Pending'

    def test_mark_payment_completed_is_idempotent_single_save(self, order):
        payment = get_provider('cash').create_payment(order, order.total_price, 'usd')
        assert payment.status == 'Pending'
        assert order.status == 'Pending'

        with mock.patch('payments.services._send_notification') as mocked_notif:
            payment.save = mock.Mock(wraps=payment.save)
            order.save = mock.Mock(wraps=order.save)
            p1 = services.mark_payment_completed(payment, is_cash=True)
            services.mark_payment_completed(p1)

        assert p1.status == 'Completed'
        order.refresh_from_db()
        assert order.status == 'Confirmed'
        mocked_notif.assert_called_once()
        assert payment.save.call_count == 1
        assert order.save.call_count == 1

    def test_checkout_page_has_csrf_and_fetch_header(self, order, site_settings, client):
        resp = client.get(reverse('payments:process', args=[order.id]))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'X-CSRFToken' in content
        assert 'csrfmiddlewaretoken' in content

    def test_create_checkout_session_rejects_missing_csrf(self, order, site_settings):
        client = Client(enforce_csrf_checks=True)
        url = reverse('payments:create_checkout_session', args=[order.id])
        resp = client.post(url, data=json.dumps({}), content_type='application/json')
        assert resp.status_code == 302
        assert resp.get('Location') == reverse('home')

    def test_create_checkout_session_with_csrf_and_mock(self, order, site_settings):
        client = Client(enforce_csrf_checks=True)
        page = client.get(reverse('payments:process', args=[order.id]))
        token = page.cookies['csrftoken'].value
        session_mock = mock.MagicMock()
        session_mock.id = 'cs_test_csrf'
        session_mock.url = 'https://checkout.stripe.com/pay/cs_test_csrf'
        url = reverse('payments:create_checkout_session', args=[order.id])
        with mock.patch('payments.providers.stripe_provider.stripe.checkout.Session.create', return_value=session_mock):
            resp = client.post(url, data=json.dumps({}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
        assert resp.status_code == 200
        assert resp.json()['url'] == 'https://checkout.stripe.com/pay/cs_test_csrf'

    def test_stripe_success_and_cancel_url_contain_host_and_order(self, order, site_settings):
        req = RequestFactory().get('/')
        req.is_secure = lambda: False
        req.get_host = lambda: 'example.com'
        session_mock = mock.MagicMock()
        session_mock.id = 'cs_test_url'
        session_mock.url = 'https://checkout.stripe.com/pay/cs_test_url'
        with mock.patch('payments.providers.stripe_provider.stripe.checkout.Session.create', return_value=session_mock) as mocked:
            services.initiate_payment(order, 'stripe', request=req)
        _, kwargs = mocked.call_args
        assert kwargs['success_url'] == f'http://example.com/payments/stripe/success/{order.id}/'
        assert kwargs['cancel_url'] == f'http://example.com/payments/stripe/cancel/{order.id}/'

    def test_process_page_renders_enabled_providers(self, order, site_settings, client):
        resp = client.get(reverse('payments:process', args=[order.id]))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'value="cash"' in content
        assert 'value="stripe"' in content
        assert 'الدفع عند الاستلام' in content
        assert 'بطاقة إئتمانية' in content

    def test_process_page_hides_disabled_stripe(self, order, db):
        cache.clear()
        SiteSettings.objects.create(
            stripe_publishable_key='pk_test_x',
            stripe_secret_key='sk_test_x',
            stripe_mode='disabled',
        )
        resp = Client().get(reverse('payments:process', args=[order.id]))
        content = resp.content.decode('utf-8')
        assert resp.status_code == 200
        assert 'value="cash"' in content
        assert 'value="stripe"' not in content
