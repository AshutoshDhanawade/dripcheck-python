from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPRecord


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('accounts.views.Client')
    def test_signup_rejects_existing_mobile_number(self, mock_client):
        User.objects.create(mobile_no='+919999999999', is_active=True)

        response = self.client.post(reverse('signup'), {'mobile_no': '+919999999999'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', str(response.data).lower())
        mock_client.assert_not_called()

    def test_onboarding_requires_all_answers_to_be_true(self):
        user = User.objects.create(mobile_no='+919988776655', is_active=True)
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.post(reverse('onboarding_submit'), {
            'responses': {'q1': False, 'q2': True},
            'full_name': 'Test User',
            'email': 'test@example.com',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_onboarded)

        response = self.client.post(reverse('onboarding_submit'), {
            'responses': {'q1': True, 'q2': True},
            'full_name': 'Test User',
            'email': 'test@example.com',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_onboarded)
