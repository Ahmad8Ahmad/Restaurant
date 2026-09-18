from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class SettingsProfileSaveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@example.com', username='old_name', password='pass12345',
            role='restaurant', is_active=True, is_verified=True, is_approved=True,
        )
        self.client.login(email='owner@example.com', password='pass12345')

    def test_profile_save_does_not_500(self):
        response = self.client.post(reverse('user_settings:settings'), {
            'section': 'profile',
            'username': 'new_name',
            'email': 'owner@example.com',
            'phone': '+963900000000',
            'address': 'Damascus',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'new_name')

    def test_preferences_save_does_not_500(self):
        response = self.client.post(reverse('user_settings:settings'), {
            'section': 'preferences',
            'theme': 'dark',
            'notify_order_updates': 'on',
            'notify_promotions': '',
            'notify_email': 'on',
        })
        self.assertEqual(response.status_code, 302)
        from user_settings.models import UserPreference
        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(pref.theme, 'dark')
        self.assertTrue(pref.notify_order_updates)