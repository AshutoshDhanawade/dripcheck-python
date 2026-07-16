from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPRecord, OnboardingQuestion, UserOnboardingResponse


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

    def test_public_onboarding_stores_question_text_answers(self):
        user = User.objects.create(mobile_no='+919988776655', is_active=True)
        OnboardingQuestion.objects.create(
            text="What's Your Fashion Style?",
            question_type='multiple_choice',
            order=1,
        )
        OnboardingQuestion.objects.create(
            text='What Clothes Do You Wear Most?',
            question_type='multiple_choice',
            order=2,
        )
        OnboardingQuestion.objects.create(
            text='What Colors Do You Prefer Wearing?',
            question_type='multiple_choice',
            order=3,
        )
        OnboardingQuestion.objects.create(
            text='What Do You Want DripCheck To Help You With?',
            question_type='multiple_choice',
            order=4,
        )
        OnboardingQuestion.objects.create(
            text='How often do you buy clothes?',
            question_type='single_choice',
            order=5,
        )

        response = self.client.post(reverse('public_onboarding_submit'), {
            'mobile_no': user.mobile_no,
            'full_name': 'Test User',
            'email': 'test@example.com',
            'responses': {
                'fullName': 'Test User',
                'username': 'testuser',
                'email': 'test@example.com',
                'styles': ['Casual', 'Streetwear', 'Formal'],
                'clothes': ['Hoodies'],
                'colors': [{'color': '#000000', 'label': 'Black', 'value': 'Black'}],
                'goal': ['Matching Clothes From My Wardrobe'],
                'buyingFrequency': ['Every Few Months'],
            },
        }, format='json')

        self.assertEqual(response.status_code, 200)
        onboarding_response = UserOnboardingResponse.objects.get(user=user)
        self.assertEqual(onboarding_response.responses, {
            "What's Your Fashion Style?": ['Casual', 'Streetwear', 'Formal'],
            'What Clothes Do You Wear Most?': ['Hoodies'],
            'What Colors Do You Prefer Wearing?': ['Black'],
            'What Do You Want DripCheck To Help You With?': ['Matching Clothes From My Wardrobe'],
            'How often do you buy clothes?': ['Every Few Months'],
        })
