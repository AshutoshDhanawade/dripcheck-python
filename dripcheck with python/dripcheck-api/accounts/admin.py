from django.contrib import admin
from .models import User, OTPRecord, OnboardingQuestion, OnboardingOption, UserOnboardingResponse

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('mobile_no', 'full_name', 'email', 'is_active', 'is_onboarded', 'ip_address')
    list_filter = ('is_active', 'is_onboarded')
    search_fields = ('mobile_no', 'full_name', 'email')

@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ('mobile_no', 'otp', 'created_at')
    search_fields = ('mobile_no',)

class OnboardingOptionInline(admin.TabularInline):
    model = OnboardingOption
    extra = 1

@admin.register(OnboardingQuestion)
class OnboardingQuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'question_type', 'order', 'is_active')
    list_filter = ('question_type', 'is_active')
    search_fields = ('text',)
    inlines = [OnboardingOptionInline]

@admin.register(UserOnboardingResponse)
class UserOnboardingResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'completed_at')
    search_fields = ('user__mobile_no', 'user__full_name')
