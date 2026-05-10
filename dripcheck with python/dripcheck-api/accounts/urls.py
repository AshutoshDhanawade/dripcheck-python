from django.urls import path
from .views import SignupView, VerifyOTPView, LoginView, OnboardingQuestionsView, OnboardingSubmitView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('onboarding/questions/', OnboardingQuestionsView.as_view(), name='onboarding_questions'),
    path('onboarding/submit/', OnboardingSubmitView.as_view(), name='onboarding_submit'),
]
