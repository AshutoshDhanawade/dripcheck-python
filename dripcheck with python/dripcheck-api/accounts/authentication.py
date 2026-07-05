from rest_framework_simplejwt.authentication import JWTAuthentication


class BearerTokenAuthentication(JWTAuthentication):
    """JWT authentication that accepts `Authorization: Bearer <token>`."""
    pass
