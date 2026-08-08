from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView,
    VerifyOTPView,
    LoginView,
    OnboardingQuestionsView,
    OnboardingSubmitView,
    PublicOnboardingSubmitView,
    OnboardingPreferencesView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('onboarding/questions/', OnboardingQuestionsView.as_view(), name='onboarding_questions'),
    path('onboarding/submit/', OnboardingSubmitView.as_view(), name='onboarding_submit'),
    path('onboarding/public-submit/', PublicOnboardingSubmitView.as_view(), name='public_onboarding_submit'),
    path('onboarding/preferences/', OnboardingPreferencesView.as_view(), name='onboarding_preferences'),
]
