from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from restaurants.models import Restaurant


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
            {'name': 'Hacked', 'is_approved': True, 'is_trendy': True, 'is_active': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, 'Hacked')
        self.assertFalse(self.restaurant.is_approved)
        self.assertFalse(self.restaurant.is_trendy)
        self.assertTrue(self.restaurant.is_active)

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
