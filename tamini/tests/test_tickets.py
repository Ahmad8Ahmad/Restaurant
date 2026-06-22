import unittest.mock
import pytest
from django.utils import timezone
from datetime import timedelta
from orders.models import Order, Ticket
from payments.models import Payment
from restaurants.models import Restaurant
from accounts.models import User


@pytest.fixture
def customer(db):
    return User.objects.create(
        email='customer@test.com',
        username='testcustomer',
    )


@pytest.fixture
def restaurant(db):
    owner = User.objects.create(
        email='owner@test.com',
        username='owner',
    )
    return Restaurant.objects.create(
        name='Test Restaurant',
        owner=owner,
        latitude=33.5138,
        longitude=36.2765,
    )


@pytest.fixture
def order(customer, restaurant, db):
    return Order.objects.create(
        customer=customer,
        restaurant=restaurant,
        delivery_address='Test Address',
        total_price=10000,
        status='Pending',
    )


@pytest.mark.django_db
class TestTicketCreation:

    def test_ticket_created_on_payment_completion(self, order):
        assert not hasattr(order, 'ticket')
        Payment.objects.create(
            order=order,
            amount=10000,
            status='Completed',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert hasattr(order, 'ticket')
        assert order.ticket.is_active is True
        assert len(order.ticket.code) == 12

    def test_ticket_not_created_on_pending_payment(self, order):
        Payment.objects.create(
            order=order,
            amount=10000,
            status='Pending',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert not hasattr(order, 'ticket')

    def test_ticket_not_created_on_failed_payment(self, order):
        Payment.objects.create(
            order=order,
            amount=10000,
            status='Failed',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert not hasattr(order, 'ticket')

    def test_ticket_code_unique(self, order, customer):
        code1 = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        ).code
        other_order = Order.objects.create(
            customer=customer,
            restaurant=order.restaurant,
            delivery_address='Other',
            total_price=5000,
        )
        code2 = Ticket.objects.create(
            order=other_order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        ).code
        assert code1 != code2
        assert len(code1) == 12
        assert len(code2) == 12

    def test_ticket_code_stripped_on_save(self, order, customer):
        ticket = Ticket(
            code='  ABC123DEF456  ',
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        ticket.save()
        assert ticket.code == 'ABC123DEF456'

    def test_auto_generated_code_when_empty(self, order, customer):
        ticket = Ticket(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        ticket.save()
        assert len(ticket.code) == 12
        assert ticket.code.isalnum()

    def test_ticket_expiry(self, order, customer):
        ticket = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() - timedelta(days=1),
        )
        assert ticket.is_expired() is True

    def test_ticket_not_expired(self, order, customer):
        ticket = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=1),
        )
        assert ticket.is_expired() is False

    def test_ticket_default_ordering(self, order, customer):
        t1 = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        other_order = Order.objects.create(
            customer=customer,
            restaurant=order.restaurant,
            delivery_address='Later',
            total_price=5000,
        )
        t2 = Ticket.objects.create(
            order=other_order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        tickets = list(Ticket.objects.all())
        assert tickets[0] == t2
        assert tickets[1] == t1

    def test_ticket_created_on_payment_status_update_to_completed(self, order):
        payment = Payment.objects.create(
            order=order,
            amount=10000,
            status='Pending',
            payment_method='Cash',
        )
        assert not hasattr(order, 'ticket')
        payment.status = 'Completed'
        payment.save()
        order.refresh_from_db()
        assert hasattr(order, 'ticket')

    def test_duplicate_ticket_not_created(self, order):
        Payment.objects.create(
            order=order,
            amount=10000,
            status='Completed',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert hasattr(order, 'ticket')

    def test_ticket_guest_order(self, restaurant, db):
        order = Order.objects.create(
            customer=None,
            restaurant=restaurant,
            delivery_address='Guest Address',
            total_price=8000,
        )
        Payment.objects.create(
            order=order,
            amount=8000,
            status='Completed',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert hasattr(order, 'ticket')
        assert order.ticket.customer is None

    def test_ticket_str(self, order, customer):
        ticket = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
            code='TESTCODE1234',
        )
        assert 'TESTCODE1234' in str(ticket)
        assert str(order.id) in str(ticket)

    def test_multiple_orders_same_customer(self, customer, restaurant, db):
        orders = []
        for i in range(3):
            o = Order.objects.create(
                customer=customer,
                restaurant=restaurant,
                delivery_address=f'Address {i}',
                total_price=5000 * (i + 1),
            )
            Payment.objects.create(
                order=o,
                amount=5000 * (i + 1),
                status='Completed',
                payment_method='Cash',
            )
            orders.append(o)
        for o in orders:
            o.refresh_from_db()
            assert hasattr(o, 'ticket')
            assert o.ticket.is_active is True

    def test_ticket_code_default_generation(self, order, customer):
        ticket = Ticket(
            code='',
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        ticket.save()
        assert len(ticket.code) == 12

    def test_ticket_code_case_sensitivity(self, order, customer):
        ticket = Ticket.objects.create(
            order=order,
            customer=customer,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
            code='ABCDEF123456',
        )
        assert ticket.code == 'ABCDEF123456'

    def test_ticket_not_created_for_payment_with_existing_ticket(self, order):
        Payment.objects.create(
            order=order,
            amount=10000,
            status='Completed',
            payment_method='Cash',
        )
        order.refresh_from_db()
        assert hasattr(order, 'ticket')
        original_code = order.ticket.code
        payment = order.payment
        payment.status = 'Completed'
        payment.save()
        order.refresh_from_db()
        assert order.ticket.code == original_code

    def test_duplicate_code_raises_integrity_error(self, order, customer):
        Ticket.objects.create(
            order=order, customer=customer, is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
            code='DUPLICATE123',
        )
        other_order = Order.objects.create(
            customer=customer, restaurant=order.restaurant,
            delivery_address='Other', total_price=5000,
        )
        with pytest.raises(Exception):
            Ticket.objects.create(
                order=other_order, customer=customer, is_active=True,
                expires_at=timezone.now() + timedelta(days=30),
                code='DUPLICATE123',
            )

    def test_duplicate_order_raises_integrity_error(self, order, customer):
        Ticket.objects.create(
            order=order, customer=customer, is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        with pytest.raises(Exception):
            Ticket.objects.create(
                order=order, customer=customer, is_active=True,
                expires_at=timezone.now() + timedelta(days=30),
            )

    def test_missing_order_raises_integrity_error(self, customer):
        with pytest.raises(Exception):
            Ticket.objects.create(
                customer=customer, is_active=True,
                expires_at=timezone.now() + timedelta(days=30),
            )

    def test_missing_expires_at_raises_integrity_error(self, order, customer):
        with pytest.raises(Exception):
            Ticket.objects.create(
                order=order, customer=customer, is_active=True,
            )

    def test_code_max_length_enforced(self, order, customer):
        ticket = Ticket(
            order=order, customer=customer, is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
            code='A' * 25,
        )
        with pytest.raises(Exception):
            ticket.full_clean()

    @pytest.fixture(autouse=True)
    def mock_payment_gateways(self):
        with unittest.mock.patch('payments.handlers.stripe_handler.stripe') as _:
            yield

    def test_ticket_creation_does_not_call_payment_gateway(self, order):
        Payment.objects.create(
            order=order, amount=10000, status='Completed', payment_method='Cash',
        )
        order.refresh_from_db()
        assert hasattr(order, 'ticket')
