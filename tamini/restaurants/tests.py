from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from restaurants.models import Restaurant, MenuItem, Category


def make_png(filename):
    buf = BytesIO()
    Image.new('RGB', (50, 50), 'red').save(buf, format='PNG')
    return SimpleUploadedFile(filename, buf.getvalue(), content_type='image/png')


class RestaurantUpdateAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com', username='owner', password='pass12345', role='restaurant'
        )
        self.other_owner = User.objects.create_user(
            email='other@example.com', username='other', password='pass12345', role='restaurant'
        )
        self.customer = User.objects.create_user(
            email='customer@example.com', username='customer', password='pass12345', role='customer'
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Old Name', description='Old desc', is_approved=False
        )

    def patch_url(self):
        return f'/api/restaurants/{self.restaurant.id}/'

    def test_owner_can_partial_update_with_multipart(self):
        self.client.force_authenticate(self.owner)
        logo = make_png('logo.png')
        cover = make_png('cover.png')
        response = self.client.patch(
            self.patch_url(),
            {
                'name': 'New Name',
                'description': 'New desc',
                'address': '123 Main St',
                'phone': '+962700000000',
                'logo': logo,
                'cover_image': cover,
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, 'New Name')
        self.assertEqual(self.restaurant.description, 'New desc')
        self.assertEqual(self.restaurant.address, '123 Main St')
        self.assertEqual(self.restaurant.phone, '+962700000000')
        self.assertTrue(self.restaurant.logo.name.startswith('restaurant_logos/logo'))
        self.assertTrue(self.restaurant.cover_image.name.startswith('restaurant_covers/cover'))
        self.assertTrue(self.restaurant.logo.name.endswith('.webp'))
        self.assertTrue(self.restaurant.cover_image.name.endswith('.webp'))

    def test_owner_cannot_patch_admin_only_fields(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            self.patch_url(),
            {'name': 'Hacked', 'is_approved': True, 'is_trendy': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, 'Hacked')
        self.assertFalse(self.restaurant.is_approved)
        self.assertFalse(self.restaurant.is_trendy)

    def test_owner_can_patch_is_active(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            self.patch_url(),
            {'is_active': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.is_active)

    def test_other_owner_cannot_update(self):
        self.client.force_authenticate(self.other_owner)
        response = self.client.patch(self.patch_url(), {'name': 'Stolen'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_update(self):
        self.client.force_authenticate(self.customer)
        response = self.client.patch(self.patch_url(), {'name': 'Stolen'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_update(self):
        response = self.client.patch(self.patch_url(), {'name': 'Stolen'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_cannot_update_another_restaurant_of_another_owner(self):
        other = Restaurant.objects.create(
            owner=self.other_owner, name='Other', is_approved=True
        )
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f'/api/restaurants/{other.id}/', {'name': 'Stolen'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MultiRestaurantDashboardTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com', username='owner', password='pass12345',
            role='restaurant', is_active=True, is_verified=True, is_approved=True,
        )
        self.r1 = Restaurant.objects.create(owner=self.owner, name='Restaurant One', is_approved=True)
        self.r2 = Restaurant.objects.create(owner=self.owner, name='Restaurant Two', is_approved=True)
        self.category = Category.objects.create(name='Food')
        self.client.login(email='owner@example.com', password='pass12345')

    def test_dashboard_renders_switcher_for_multi_owner(self):
        response = self.client.get(reverse('restaurants:restaurant_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="restaurant-switcher"')
        self.assertContains(response, 'Restaurant One')
        self.assertContains(response, 'Restaurant Two')

    def test_dashboard_uses_selected_restaurant(self):
        response = self.client.get(
            reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r2.id}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['restaurant'].id, self.r2.id)

    def test_add_menu_item_uses_session_selection(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r2.id}')
        response = self.client.post(reverse('restaurants:add_menu_item'), {
            'category': self.category.id,
            'name': 'Kebab',
            'price': '5000',
        })
        self.assertRedirects(
            response, reverse('restaurants:restaurant_dashboard'), fetch_redirect_response=False,
        )
        item = MenuItem.objects.get(name='Kebab')
        self.assertEqual(item.restaurant_id, self.r2.id)

    def test_add_discount_targets_selected_restaurant(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r2.id}')
        self.r1_menu = MenuItem.objects.create(
            restaurant=self.r1, category=self.category, name='From One', price=1000,
        )
        self.r2_menu = MenuItem.objects.create(
            restaurant=self.r2, category=self.category, name='From Two', price=2000,
        )
        response = self.client.post(reverse('restaurants:add_discount'), {
            'item_id': self.r2_menu.id,
            'new_price': '1500',
        })
        self.assertEqual(response.status_code, 302)
        self.r2_menu.refresh_from_db()
        from decimal import Decimal
        self.assertEqual(self.r2_menu.discount_price, Decimal('1500'))

    def test_add_discount_rejects_item_from_other_restaurant(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r2.id}')
        self.r1_menu = MenuItem.objects.create(
            restaurant=self.r1, category=self.category, name='From One', price=1000,
        )
        response = self.client.post(reverse('restaurants:add_discount'), {
            'item_id': self.r1_menu.id,
            'new_price': '500',
        })
        self.assertEqual(response.status_code, 404)

    def test_update_settings_targets_selected_restaurant(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r2.id}')
        response = self.client.post(reverse('restaurants:update_restaurant_settings'), {
            'name': 'Two Renamed',
        })
        self.assertEqual(response.status_code, 302)
        self.r2.refresh_from_db()
        self.assertEqual(self.r2.name, 'Two Renamed')
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.name, 'Restaurant One')

    def test_update_settings_persists_is_active(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r1.id}')
        response = self.client.post(reverse('restaurants:update_restaurant_settings'), {
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.r1.refresh_from_db()
        self.assertTrue(self.r1.is_active)
        response = self.client.post(reverse('restaurants:update_restaurant_settings'), {
            'is_active': '',
        })
        self.assertEqual(response.status_code, 302)
        self.r1.refresh_from_db()
        self.assertFalse(self.r1.is_active)

    def test_toggle_active_web_view_toggles(self):
        self.client.get(reverse('restaurants:restaurant_dashboard') + f'?restaurant={self.r1.id}')
        response = self.client.post(reverse('restaurants:toggle_active'))
        self.assertRedirects(
            response, reverse('restaurants:restaurant_dashboard'), fetch_redirect_response=False,
        )
        self.r1.refresh_from_db()
        self.assertFalse(self.r1.is_active)

    def test_restaurant_list_hides_closed_restaurant(self):
        self.r1.is_active = False
        self.r1.save(update_fields=['is_active'])
        response = self.client.get(reverse('restaurants:restaurant_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Restaurant One')
        self.assertContains(response, 'Restaurant Two')

    def test_checkout_blocks_closed_restaurant(self):
        from orders.models import Order

        self.r1.is_active = False
        self.r1.save(update_fields=['is_active'])
        mi = MenuItem.objects.create(restaurant=self.r1, category=self.category, name='Kebab', price=1000)
        self.client.post(reverse('orders:add_to_cart', args=[mi.id]), {'quantity': 1})
        response = self.client.post(reverse('orders:checkout'), {
            'delivery_address': 'Damascus',
            'customer_phone': '0999',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(restaurant=self.r1).exists())
