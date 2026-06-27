from rest_framework.permissions import AllowAny
import random
from django.conf import settings
from twilio.rest import Client
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from .serializers import SignupSerializer, VerifyOTPSerializer, LoginSerializer
from .models import User, OTPRecord
from api.models import WardrobeItem
from api.serializers import WardrobeItemSerializer
from bundle_generate.models import MerchantProduct
from bundle_generate.serializers import MerchantProductSerializer

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class SignupView(APIView):
    def post(self, request):
        try:
            serializer = SignupSerializer(data=request.data)
            if serializer.is_valid():
                mobile_no = serializer.validated_data['mobile_no']
                
                # Generate a 6-digit OTP
                otp = str(random.randint(1000, 9999))
                print("otp",otp)
                
                # Save OTP to database
                OTPRecord.objects.create(mobile_no=mobile_no, otp=otp)
                
                # Send OTP via SMS using Twilio
                try:
                    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    message = client.messages.create(
                        body=f"Your Dripcheck verification code is: {otp}",
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=mobile_no
                    )
                except Exception as sms_e:
                    print(f"Failed to send SMS via Twilio: {sms_e}")
                    # You might want to log this or handle it differently in production
                    
                # Also print to console for development convenience
                print(f"--- OTP for {mobile_no} is: {otp} ---")
                
                return Response({"message": "OTP sent successfully."}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during signup.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyOTPView(APIView):
    def post(self, request):
        try:
            serializer = VerifyOTPSerializer(data=request.data)
            if serializer.is_valid():
                mobile_no = serializer.validated_data['mobile_no']
                
                # Get the user's IP address
                ip_address = get_client_ip(request)
                
                # Create or update user
                user, created = User.objects.get_or_create(
                    mobile_no=mobile_no,
                    defaults={'ip_address': ip_address, 'is_active': True}
                )
                
                if not created:
                    user.is_active = True
                    user.ip_address = ip_address
                    user.save()

                # Delete used OTP
                OTPRecord.objects.filter(mobile_no=mobile_no).delete()
                
                return Response({"message": "Registration complete. User verified."}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during OTP verification.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LoginView(APIView):
    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data)
            if serializer.is_valid():
                mobile_no = serializer.validated_data['mobile_no']
                user = User.objects.get(mobile_no=mobile_no)
                
                # Generate or get existing token
                token, created = Token.objects.get_or_create(user=user)
                
                response_data = {
                    "token": token.key,
                    "message": "Login successful.",
                    "is_new_user": not user.is_onboarded,
                    "wardrobe": []
                }
                
                wardrobe_empty = True
                if user.is_onboarded:
                    wardrobe_items = WardrobeItem.objects.filter(user_id=mobile_no)
                    if wardrobe_items.exists():
                        wardrobe_serializer = WardrobeItemSerializer(wardrobe_items, many=True)
                        response_data["wardrobe"] = wardrobe_serializer.data
                        wardrobe_empty = False
                        
                if wardrobe_empty:
                    products = MerchantProduct.objects.all().order_by('-sales_count')[:10]
                    product_serializer = MerchantProductSerializer(products, many=True)
                    response_data["best_selling_products"] = product_serializer.data
                
                return Response(response_data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during login.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

from rest_framework.permissions import IsAuthenticated
from .models import OnboardingQuestion, UserOnboardingResponse
from .serializers import OnboardingQuestionSerializer, OnboardingSubmitSerializer

class OnboardingQuestionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            questions = OnboardingQuestion.objects.filter(is_active=True).order_by('order')
            serializer = OnboardingQuestionSerializer(questions, many=True)
            return Response({"questions": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred while fetching questions.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OnboardingSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            serializer = OnboardingSubmitSerializer(data=request.data)
            if serializer.is_valid():
                responses = serializer.validated_data['responses']
                full_name = serializer.validated_data.get('full_name', '')
                email = serializer.validated_data.get('email', '')

                user = request.user
                if full_name:
                    user.full_name = full_name
                if email:
                    user.email = email
                
                user.is_onboarded = True
                user.save()

                # Save or update responses
                UserOnboardingResponse.objects.update_or_create(
                    user=user,
                    defaults={'responses': responses}
                )

                return Response({"message": "Onboarding completed successfully."}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during onboarding submission.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
