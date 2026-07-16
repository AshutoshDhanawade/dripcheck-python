from django.urls import path
from .views import (
    SignupView,
    VerifyOTPView,
    LoginView,
    OnboardingQuestionsView,
    OnboardingSubmitView,
    PublicOnboardingSubmitView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('onboarding/questions/', OnboardingQuestionsView.as_view(), name='onboarding_questions'),
    path('onboarding/submit/', OnboardingSubmitView.as_view(), name='onboarding_submit'),
    path('onboarding/public-submit/', PublicOnboardingSubmitView.as_view(), name='public_onboarding_submit'),
]
