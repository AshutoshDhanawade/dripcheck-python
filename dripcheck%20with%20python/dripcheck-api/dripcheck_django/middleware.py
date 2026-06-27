import logging

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware:
    """Middleware that logs each incoming request URL to the terminal."""
    def __init__(self, get_response):
        self.get_response = get_response
        # Configure logger to output to console
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def __call__(self, request):
        # Log the request path and method
        logger.info(f"Incoming request: {request.method} {request.get_full_path()}")
        response = self.get_response(request)
        return response
