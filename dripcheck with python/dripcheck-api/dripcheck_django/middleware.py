import logging

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware:
    """Middleware that logs each incoming request to the terminal."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logger.info(f"→ {request.method} {request.get_full_path()}")
        response = self.get_response(request)
        logger.info(f"← {response.status_code} {request.method} {request.get_full_path()}")
        return response
