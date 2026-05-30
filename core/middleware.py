# core/middleware.py
import logging
import time

# creates a logger named 'nagriksetu.requests'
logger = logging.getLogger('nagriksetu.requests')

class RequestLogMiddleware:
    """
    Logs every request:
    - Who made it (user)
    - What they requested (method + path)
    - How long it took (ms)
    - What response they got (status code)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # this runs once when server starts

    def __call__(self, request):
        # ── BEFORE VIEW runs ──────────────────────────────
        start_time = time.time()

        # get username — anonymous if not logged in
        user = request.user.username if hasattr(request, 'user') \
               and request.user.is_authenticated else 'anonymous'

        # ── VIEW runs here ────────────────────────────────
        response = self.get_response(request)

        # ── AFTER VIEW runs ───────────────────────────────
        duration_ms = (time.time() - start_time) * 1000

        # log the request
        logger.info(
            f"{user} | {request.method} {request.path} "
            f"| {response.status_code} | {duration_ms:.0f}ms"
        )

        # also print to terminal during development
        print(
            f"[LOG] {user} | {request.method} {request.path} "
            f"| {response.status_code} | {duration_ms:.0f}ms"
        )

        return response