# core/middleware.py
"""Request logging middleware."""
import logging
import time
import uuid

from .logging import request_id_var

logger = logging.getLogger('nagriksetu.requests')

# Noise we never want in the log.
IGNORED_PREFIXES = ('/static/', '/media/', '/favicon.ico', '/healthz/')

# Anything slower than this is worth flagging as a warning.
SLOW_REQUEST_MS = 1000


class RequestLogMiddleware:
    """
    Logs who called what, how long it took, and what came back.

    Also assigns a short request id that is returned in X-Request-ID and
    stamped on every log line written while handling the request (see
    core.logging.RequestIdFilter), so a user-reported error can be traced.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex[:12]
        token = request_id_var.set(request.request_id)
        try:
            if request.path.startswith(IGNORED_PREFIXES):
                response = self.get_response(request)
            else:
                response = self._logged(request)
            response['X-Request-ID'] = request.request_id
            return response
        finally:
            request_id_var.reset(token)

    def _logged(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        user = 'anonymous'
        if hasattr(request, 'user') and request.user.is_authenticated:
            user = f'user:{request.user.pk}[{getattr(request.user, "role", "?")}]'

        message = f'{user} | {request.method} {request.path} | {response.status_code} | {duration_ms:.0f}ms'
        if response.status_code >= 500:
            logger.error(message)
        elif response.status_code >= 400 or duration_ms > SLOW_REQUEST_MS:
            logger.warning(message)
        else:
            logger.info(message)
        return response
