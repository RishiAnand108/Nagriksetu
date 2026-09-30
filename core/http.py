# core/http.py
"""Small request helpers shared by the HTML views."""
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback: str) -> str:
    """Follow a posted/queried ?next= only if it points back at this site."""
    candidate = request.POST.get('next') or request.GET.get('next')
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def client_ip(request) -> str:
    """
    Best-effort client address for rate limiting.

    X-Forwarded-For is only honoured when the app is known to sit behind a
    proxy that sets it (Render, nginx); otherwise anyone could spoof it.
    """
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_ajax(request) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
