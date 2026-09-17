import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.models import User
from support.models import Ticket, SUPPORT_AGENT_GROUP


@pytest.fixture
def customer(db):
    return User.objects.create(
        email='customer@test.com',
        username='customer',
        phone='+963900000001',
    )


@pytest.fixture
def agent1(db):
    return User.objects.create(email='agent1@test.com', username='agent1')


@pytest.fixture
def agent2(db):
    return User.objects.create(email='agent2@test.com', username='agent2')


@pytest.fixture
def a_superuser(db):
    return User.objects.create_superuser(
        email='boss@test.com', username='boss', password='x'
    )


def make_agent(user):
    group, _ = Group.objects.get_or_create(name=SUPPORT_AGENT_GROUP)
    user.groups.add(group)
    return user


@pytest.fixture
def support_ticket(customer):
    return Ticket.objects.create(
        customer=customer,
        customer_name=customer.username,
        customer_email=customer.email,
        subject='استفسار',
        description='أريد مساعدة',
        status='open',
        priority='medium',
    )


def queue_url(**params):
    from urllib.parse import urlencode
    return reverse('support:manage_tickets') + ('?' + urlencode(params) if params else '')


@pytest.mark.django_db
class TestAgentAccess:

    def test_customer_cannot_access_console(self, client, customer):
        client.force_login(customer)
        resp = client.get(reverse('support:manage_tickets'))
        assert resp.status_code in (301, 302)

    def test_superuser_can_access_console(self, client, a_superuser):
        client.force_login(a_superuser)
        resp = client.get(reverse('support:manage_tickets'))
        assert resp.status_code == 200
        assert 'دعم العملاء' in resp.content.decode()

    def test_group_agent_can_access_console(self, client, agent1):
        client.force_login(make_agent(agent1))
        resp = client.get(reverse('support:manage_tickets'))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestClaimFlow:

    def test_agent_can_claim_ticket(self, client, agent1, support_ticket):
        agent = make_agent(agent1)
        client.force_login(agent)
        resp = client.post(
            reverse('support:manage_ticket_detail', args=[support_ticket.id]),
            {'action': 'claim'},
        )
        assert resp.status_code in (301, 302)
        support_ticket.refresh_from_db()
        assert support_ticket.assignee == agent
        assert support_ticket.status == 'in_progress'

    def test_second_agent_cannot_claim_claimed_ticket(self, client, agent1, agent2, support_ticket):
        agent_a = make_agent(agent1)
        agent_b = make_agent(agent2)
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=agent_a)
        client.force_login(agent_b)
        client.post(reverse('support:manage_ticket_detail', args=[support_ticket.id]), {'action': 'claim'})
        support_ticket.refresh_from_db()
        assert support_ticket.assignee == agent_a

    def test_other_agent_is_blocked(self, client, agent1, agent2, support_ticket):
        agent_a = make_agent(agent1)
        make_agent(agent2)
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=agent_a)
        client.force_login(agent2)
        resp = client.get(reverse('support:manage_ticket_detail', args=[support_ticket.id]))
        body = resp.content.decode()
        assert 'قيد المتابعة من' in body
        assert 'إضافة رد' not in body

    def test_assignee_can_reply(self, client, agent1, support_ticket):
        agent = make_agent(agent1)
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=agent)
        client.force_login(agent)
        resp = client.post(
            reverse('support:manage_ticket_detail', args=[support_ticket.id]),
            {'message': 'تمت المتابعة'},
        )
        assert resp.status_code in (301, 302)
        assert support_ticket.messages.filter(message='تمت المتابعة').exists()

    def test_other_agent_cannot_reply(self, client, agent1, agent2, support_ticket):
        agent_a = make_agent(agent1)
        make_agent(agent2)
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=agent_a)
        client.force_login(agent2)
        client.post(
            reverse('support:manage_ticket_detail', args=[support_ticket.id]),
            {'message': 'أنا أتدخل'},
        )
        assert not support_ticket.messages.filter(message='أنا أتدخل').exists()

    def test_assignee_can_unclaim(self, client, agent1, support_ticket):
        agent = make_agent(agent1)
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=agent)
        client.force_login(agent)
        client.post(
            reverse('support:manage_ticket_detail', args=[support_ticket.id]),
            {'action': 'unclaim'},
        )
        support_ticket.refresh_from_db()
        assert support_ticket.assignee is None

    def test_unclaimed_ticket_is_in_queue(self, client, agent1, support_ticket):
        client.force_login(make_agent(agent1))
        body = client.get(queue_url(view='queue')).content.decode()
        assert '#%d' % support_ticket.id in body

    def test_claimed_ticket_not_in_queue(self, client, agent1, support_ticket):
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=make_agent(agent1))
        client.force_login(agent1)
        body = client.get(queue_url(view='queue')).content.decode()
        assert '#%d' % support_ticket.id not in body

    def test_superuser_can_open_any_ticket(self, client, a_superuser, agent1, support_ticket):
        Ticket.objects.filter(pk=support_ticket.pk).update(assignee=make_agent(agent1))
        client.force_login(a_superuser)
        resp = client.get(reverse('support:manage_ticket_detail', args=[support_ticket.id]))
        assert resp.status_code == 200
        assert 'إضافة رد' in resp.content.decode()