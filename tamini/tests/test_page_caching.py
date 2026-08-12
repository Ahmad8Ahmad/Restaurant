import pytest
from django.core.cache import cache
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

from accounts.models import User
from restaurants.models import Restaurant, MenuItem, Category, SiteContent
from tamini.page_cache import invalidate_shared_pages

HOME = '/ar/'


@pytest.fixture
def seeded(db):
    SiteContent.load()
    owner = User.objects.create(
        email='owner@test.com',
        username='owner',
        is_staff=True,
    )
    cat = Category.objects.create(name='Main')
    restaurant = Restaurant.objects.create(
        name='Test Restaurant',
        owner=owner,
        latitude=33.5138,
        longitude=36.2765,
        is_approved=True,
    )
    MenuItem.objects.create(
        name='Shawarma',
        restaurant=restaurant,
        category=cat,
        price=5000,
        is_available=True,
    )
    return restaurant


@pytest.mark.django_db
class TestSharedPageCache:

    def test_anonymous_home_is_shared_and_cookie_free(self, seeded):
        client = Client()
        response = client.get(HOME)
        assert response.status_code == 200
        assert 'Shawarma' in response.content.decode()
        # No session may be created for anonymous visitors…
        assert 'sessionid' not in response.cookies
        # …and no Vary: Cookie, otherwise each visitor gets their own cache entry.
        assert 'Cookie' not in response.get('Vary', '')
        # The page is marked cacheable.
        assert 'max-age=120' in response['Cache-Control']

    def test_second_anonymous_visitor_is_served_from_cache(self, seeded):
        first = Client().get(HOME)
        assert first.status_code == 200

        # A brand-new visitor (no cookies at all) must hit the shared entry,
        # not re-render: a cached page costs zero queries.
        with CaptureQueriesContext(connection) as ctx:
            second = Client().get(HOME)
        assert second.status_code == 200
        assert len(ctx) == 0
        assert 'Shawarma' in second.content.decode()

    def test_gzip_then_plain_visitor_both_get_valid_content(self, seeded):
        # A gzip visitor mutates the response in place (GZipMiddleware). The
        # shared entry must not keep that mutation, otherwise the next plain
        # visitor would receive gzipped bytes without a Content-Encoding.
        gz = Client().get(HOME, HTTP_ACCEPT_ENCODING='gzip')
        assert gz.status_code == 200
        assert gz['Content-Encoding'] == 'gzip'

        plain = Client().get(HOME)
        assert plain.status_code == 200
        assert 'Content-Encoding' not in plain
        assert 'Shawarma' in plain.content.decode()

    def test_restaurant_list_and_menu_pages_are_shared(self, seeded):
        for url in ('/ar/restaurants/', '/ar/restaurants/search/'):
            assert Client().get(url).status_code == 200
            with CaptureQueriesContext(connection) as ctx:
                cached = Client().get(url)
            assert cached.status_code == 200
            assert len(ctx) == 0

    def test_authenticated_user_bypasses_shared_cache(self, seeded):
        user = User.objects.create(
            email='customer@test.com',
            username='customer',
        )
        client = Client()
        client.force_login(user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(HOME)
        assert response.status_code == 200
        assert len(ctx) > 0

    def test_content_edit_invalidates_shared_pages(self, seeded):
        Client().get(HOME)
        with CaptureQueriesContext(connection) as ctx:
            cached = Client().get(HOME)
        assert len(ctx) == 0
        assert 'Shawarma' in cached.content.decode()

        # Editing a menu item bumps the shared-page version, so the next
        # anonymous request must re-render.
        MenuItem.objects.filter(name='Shawarma').update(name='Grilled Chicken')
        invalidate_shared_pages()
        with CaptureQueriesContext(connection) as ctx:
            fresh = Client().get(HOME)
        assert len(ctx) > 0
        assert 'Grilled Chicken' in fresh.content.decode()


@pytest.mark.django_db
class TestCartSummary:

    def test_anonymous_empty_cart(self, seeded):
        client = Client()
        response = client.get('/ar/orders/cart-summary/')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['cart_count'] == 0

    def test_authenticated_cart_count(self, seeded):
        user = User.objects.create(
            email='customer@test.com',
            username='customer',
        )
        from orders.models import Cart, CartItem
        cart = Cart.objects.create(user=user, session_key=None)
        CartItem.objects.create(cart=cart, menu_item_id=MenuItem.objects.first().id, quantity=2)

        client = Client()
        client.force_login(user)
        data = client.get('/ar/orders/cart-summary/').json()
        assert data['cart_count'] == 2
