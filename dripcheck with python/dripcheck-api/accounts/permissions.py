from rest_framework.permissions import BasePermission, IsAuthenticated

class IsOnboardedUser(IsAuthenticated):
    """
    Allows access only to authenticated users who have completed onboarding.
    """
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return bool(is_authenticated and request.user.is_onboarded)
