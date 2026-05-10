import phonenumbers
from rest_framework import serializers
from .models import User, OTPRecord
from django.utils import timezone
from datetime import timedelta

class SignupSerializer(serializers.Serializer):
    mobile_no = serializers.CharField()

    def validate_mobile_no(self, value):
        # Allow passing the country code, assuming '+' is present. If not, default handling can be added.
        if not value.startswith('+'):
            raise serializers.ValidationError("Mobile number must start with a country code (e.g. +91).")
        
        try:
            parsed_number = phonenumbers.parse(value)
            if not phonenumbers.is_valid_number(parsed_number):
                raise serializers.ValidationError("Invalid mobile number format.")
        except phonenumbers.NumberParseException:
            raise serializers.ValidationError("Invalid mobile number format.")

        return value

class VerifyOTPSerializer(serializers.Serializer):
    mobile_no = serializers.CharField()
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        mobile_no = data.get('mobile_no')
        otp = data.get('otp')

        try:
            # Get the most recent OTP for the mobile number
            otp_record = OTPRecord.objects.filter(mobile_no=mobile_no).latest('created_at')
        except OTPRecord.DoesNotExist:
            raise serializers.ValidationError({"otp": "No OTP found for this mobile number."})

        # Check if OTP is expired (e.g., valid for 5 minutes)
        if otp_record.created_at < timezone.now() - timedelta(minutes=5):
            raise serializers.ValidationError({"otp": "OTP has expired."})

        if otp_record.otp != otp:
            raise serializers.ValidationError({"otp": "Invalid OTP."})

        return data

class LoginSerializer(serializers.Serializer):
    mobile_no = serializers.CharField()

    def validate_mobile_no(self, value):
        try:
            user = User.objects.get(mobile_no=value)
            if not user.is_active:
                raise serializers.ValidationError("User is not active. Please complete signup.")
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this mobile number does not exist.")
        return value

from .models import OnboardingQuestion, OnboardingOption

class OnboardingOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingOption
        fields = ['id', 'text', 'is_other']

class OnboardingQuestionSerializer(serializers.ModelSerializer):
    options = OnboardingOptionSerializer(many=True, read_only=True)

    class Meta:
        model = OnboardingQuestion
        fields = ['id', 'text', 'question_type', 'order', 'options']

class OnboardingSubmitSerializer(serializers.Serializer):
    responses = serializers.JSONField(help_text="JSON payload mapping question text or ID to the user's answer.")
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_responses(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Responses must be a JSON dictionary.")
        return value
