import random
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from .serializers import SignupSerializer, VerifyOTPSerializer, LoginSerializer
from .models import User, OTPRecord

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
                otp = str(random.randint(100000, 999999))
                
                # Save OTP to database
                OTPRecord.objects.create(mobile_no=mobile_no, otp=otp)
                
                # In a real app, send OTP via SMS here. For now, print to console.
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
                
                return Response({
                    "token": token.key,
                    "message": "Login successful."
                }, status=status.HTTP_200_OK)
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
