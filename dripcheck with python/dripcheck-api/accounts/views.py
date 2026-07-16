import random
from django.conf import settings
from twilio.rest import Client
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .authentication import BearerTokenAuthentication
from .serializers import SignupSerializer, VerifyOTPSerializer, LoginSerializer, OnboardingQuestionSerializer, OnboardingSubmitSerializer
from .models import User, OTPRecord, OnboardingQuestion, UserOnboardingResponse, UserToken
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


def normalize_boolean_answer(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() == 'true'
    return False


ONBOARDING_RESPONSE_FIELD_ORDERS = {
    'styles': 1,
    'clothes': 2,
    'colors': 3,
    'goal': 4,
    'buyingFrequency': 5,
}

PROFILE_RESPONSE_FIELDS = {'fullName', 'full_name', 'username', 'email'}


def simplify_onboarding_answer(value):
    if isinstance(value, list):
        return [simplify_onboarding_answer(item) for item in value]
    if isinstance(value, dict):
        for key in ('label', 'value', 'text', 'name'):
            answer = value.get(key)
            if answer not in (None, ''):
                return answer
    return value


def build_question_answer_responses(responses, answer_mapper=simplify_onboarding_answer):
    questions = OnboardingQuestion.objects.filter(is_active=True).order_by('order')
    questions_by_id = {str(question.id): question for question in questions}
    questions_by_text = {question.text: question for question in questions}
    questions_by_order = {question.order: question for question in questions}

    formatted_responses = {}
    for key, answer in responses.items():
        response_key = str(key)
        if response_key in PROFILE_RESPONSE_FIELDS:
            continue

        question = (
            questions_by_id.get(response_key)
            or questions_by_text.get(response_key)
            or questions_by_order.get(ONBOARDING_RESPONSE_FIELD_ORDERS.get(response_key))
        )

        formatted_key = question.text if question else response_key
        formatted_responses[formatted_key] = answer_mapper(answer)

    return formatted_responses

class SignupView(APIView):
    def post(self, request):
        try:
            serializer = SignupSerializer(data=request.data)
            if serializer.is_valid():
                mobile_no = serializer.validated_data['mobile_no']

                # Generate a 6-digit OTP
                otp = str(random.randint(1000, 9999))
                print("otp", otp)
                
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
                
                user, created = User.objects.get_or_create(
                    mobile_no=mobile_no,
                    defaults={'ip_address': ip_address, 'is_active': True}
                )

                if not created:
                    user.is_active = True
                    user.ip_address = ip_address
                    user.save()

                refresh = RefreshToken.for_user(user)

                # Store tokens in new data table
                UserToken.objects.create(
                    user=user,
                    access_token=str(refresh.access_token),
                    refresh_token=str(refresh)
                )

                # Delete used OTP
                OTPRecord.objects.filter(mobile_no=mobile_no).delete()

                response_data = {
                    "message": "Registration complete. User verified.",
                    "user_id": user.id,
                    "show_onboarding": not user.is_onboarded,
                }
                
                # If user already onboarded, frontend can redirect to homepage
                if user.is_onboarded:
                    response_data["redirect_url"] = "/"
                else:
                    response_data["redirect_url"] = "/onboarding"

                # Include stored details if present

                if user.full_name:
                    response_data["full_name"] = user.full_name
                if user.email:
                    response_data["email"] = user.email

                return Response(response_data, status=status.HTTP_200_OK)
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
                
                response_data = {
                    "message": "Login successful.",
                    "is_new_user": not user.is_onboarded,
                    "show_onboarding": not user.is_onboarded,
                    "user_id": user.id,
                }

                refresh = RefreshToken.for_user(user)
                
                # Store tokens in new data table
                UserToken.objects.create(
                    user=user,
                    access_token=str(refresh.access_token),
                    refresh_token=str(refresh)
                )

                # Include stored user details when available
                if user.full_name:
                    response_data["full_name"] = user.full_name
                if user.email:
                    response_data["email"] = user.email
                
                # Get onboarding questions and answers
                questions = OnboardingQuestion.objects.filter(is_active=True).order_by('order')
                onboarding_response = getattr(user, 'onboarding_response', None)
                user_answers = onboarding_response.responses if onboarding_response else {}
                
                onboarding_data = []
                for q in questions:
                    options = [{"id": opt.id, "text": opt.text, "is_other": opt.is_other} for opt in q.options.all()]
                    q_data = {
                        "id": q.id,
                        "question_text": q.text,
                        "question_type": q.question_type,
                        "options": options,
                        "user_answer": user_answers.get(q.text, user_answers.get(str(q.id), None))
                    }
                    onboarding_data.append(q_data)
                
                response_data["onboarding_data"] = onboarding_data
                
                # If user already onboarded, frontend can redirect to homepage
                if user.is_onboarded:
                    response_data["redirect_url"] = "/"
                else:
                    response_data["redirect_url"] = "/onboarding"

                return Response(response_data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during login.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OnboardingQuestionsView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            if hasattr(request, 'user') and getattr(request.user, 'is_onboarded', False):
                return Response({"message": "User already onboarded."}, status=status.HTTP_400_BAD_REQUEST)

            questions = OnboardingQuestion.objects.filter(is_active=True).order_by('order')
            existing_responses = {}
            onboarding_response = getattr(request.user, 'onboarding_response', None)
            if onboarding_response and onboarding_response.responses:
                existing_responses = onboarding_response.responses

            pending_questions = []
            for question in questions:
                answer = existing_responses.get(question.text, existing_responses.get(str(question.id), None))
                if answer is None or not normalize_boolean_answer(answer):
                    pending_questions.append(question)

            serializer = OnboardingQuestionSerializer(pending_questions, many=True)
            return Response({"questions": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred while fetching questions.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OnboardingSubmitView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Prevent re-submission if already onboarded
            user = request.user
            if getattr(user, 'is_onboarded', False):
                return Response({"message": "User already onboarded."}, status=status.HTTP_400_BAD_REQUEST)

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

                normalized_responses = build_question_answer_responses(
                    responses,
                    answer_mapper=normalize_boolean_answer
                )

                UserOnboardingResponse.objects.update_or_create(
                    user=user,
                    defaults={'responses': normalized_responses}
                )

                questions = OnboardingQuestion.objects.filter(is_active=True).order_by('order')
                if questions.exists():
                    all_answers_true = True
                    for question in questions:
                        answer = normalized_responses.get(question.text, normalized_responses.get(str(question.id), False))
                        if not answer:
                            all_answers_true = False
                            break
                else:
                    all_answers_true = bool(normalized_responses) and all(normalized_responses.values())

                user.is_onboarded = all_answers_true
                user.save()

                return Response({
                    "message": "Onboarding updated successfully." if not all_answers_true else "Onboarding completed successfully.",
                    "show_onboarding": not all_answers_true,
                    "user_id": user.id,
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during onboarding submission.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PublicOnboardingSubmitView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            serializer = OnboardingSubmitSerializer(data=request.data)
            if serializer.is_valid():
                mobile_no = serializer.validated_data.get('mobile_no')
                if not mobile_no:
                    return Response({"error": "mobile_no is required."}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    user = User.objects.get(mobile_no=mobile_no)
                except User.DoesNotExist:
                    return Response({"error": "User with this mobile number does not exist."}, status=status.HTTP_404_NOT_FOUND)

                if getattr(user, 'is_onboarded', False):
                    return Response({"message": "User already onboarded."}, status=status.HTTP_400_BAD_REQUEST)

                responses = serializer.validated_data['responses']
                full_name = serializer.validated_data.get('full_name', '')
                email = serializer.validated_data.get('email', '')

                if full_name:
                    user.full_name = full_name
                if email:
                    user.email = email

                formatted_responses = build_question_answer_responses(responses)

                UserOnboardingResponse.objects.update_or_create(
                    user=user,
                    defaults={'responses': formatted_responses}
                )

                # Assume onboarding is complete if submission is made
                user.is_onboarded = True
                user.save()

                return Response({
                    "message": "Onboarding completed successfully.",
                    "show_onboarding": False,
                    "user_id": user.id,
                    "onboarding_data": formatted_responses,
                    "redirect_url": "/"
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred during public onboarding submission.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
