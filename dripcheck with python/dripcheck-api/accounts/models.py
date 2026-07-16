from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone

class CustomUserManager(BaseUserManager):
    def create_user(self, mobile_no, password=None, **extra_fields):
        if not mobile_no:
            raise ValueError('The Mobile Number must be set')
        user = self.model(mobile_no=mobile_no, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_no, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(mobile_no, password, **extra_fields)

class User(AbstractUser):
    username = None  # Remove username field
    mobile_no = models.CharField(max_length=20, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    
    # Onboarding fields
    full_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_onboarded = models.BooleanField(default=False)

    USERNAME_FIELD = 'mobile_no'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['mobile_no']),
            models.Index(fields=['id']),
        ]

    def __str__(self):
        return self.mobile_no

class OTPRecord(models.Model):
    mobile_no = models.CharField(max_length=20)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.mobile_no} - {self.otp}"

class OnboardingQuestion(models.Model):
    QUESTION_TYPES = (
        ('text', 'Text Input'),
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
    )
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.text

class OnboardingOption(models.Model):
    question = models.ForeignKey(OnboardingQuestion, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    is_other = models.BooleanField(default=False, help_text="Is this an 'Other' option requiring custom text?")

    def __str__(self):
        return f"{self.question.text[:30]} - {self.text}"

class UserOnboardingResponse(models.Model):
    mobile_no = models.CharField(max_length=10, null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='onboarding_response')
    responses = models.JSONField(default=dict, help_text="Stores the user's answers as JSON")
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Onboarding Response for {self.user.mobile_no}"

class UserToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tokens')
    access_token = models.TextField()
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token for {self.user.mobile_no}"
