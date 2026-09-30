# core/ratelimit.py
"""
Fixed-window rate limiting on Django's cache.

DRF throttles already guard /api/. This covers the HTML side — sign-in
(including the admin login) and complaint filing — without another
dependency. With the default local-memory cache each worker counts on its
own; set REDIS_URL so every worker shares one counter.
"""
import hashlib
from functools import wraps

from django.core.cache import cache
from django.shortcuts import render

from .http import client_ip


class RateLimit:
    def __init__(self, scope: str, limit: int, window_seconds: int):
        self.scope, self.limit, self.window = scope, limit, window_seconds

    def _key(self, ident: str) -> str:
        digest = hashlib.sha256(ident.encode()).hexdigest()[:32]
        return f'rl:{self.scope}:{digest}'

    def is_blocked(self, ident: str) -> bool:
        return (cache.get(self._key(ident)) or 0) >= self.limit

    def hit(self, ident: str) -> None:
        key = self._key(ident)
        if cache.add(key, 1, self.window):
            return
        try:
            cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, self.window)

    def reset(self, ident: str) -> None:
        cache.delete(self._key(ident))


# 5 failures per account per address, 30 per address, in 15 minutes.
LOGIN_PER_ACCOUNT = RateLimit('login-account', 5, 15 * 60)
LOGIN_PER_IP = RateLimit('login-ip', 30, 15 * 60)
COMPLAINT_FILING = RateLimit('complaint-create', 20, 60 * 60)


def _too_many(request, message):
    return render(request, 'errors/429.html', {'message': message}, status=429)


def login_throttled(view):
    """Count failed sign-ins and refuse further attempts once over the limit."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return view(request, *args, **kwargs)

        ip = client_ip(request)
        account = f"{ip}|{(request.POST.get('username') or '').strip().lower()[:150]}"
        if LOGIN_PER_ACCOUNT.is_blocked(account) or LOGIN_PER_IP.is_blocked(ip):
            return _too_many(request, 'Too many sign-in attempts. Please wait 15 minutes and try again.')

        response = view(request, *args, **kwargs)
        if request.user.is_authenticated:
            LOGIN_PER_ACCOUNT.reset(account)
        else:
            LOGIN_PER_ACCOUNT.hit(account)
            LOGIN_PER_IP.hit(ip)
        return response

    return wrapper


def filing_throttled(view):
    """Cap how many complaints one account can file per hour through the web form."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method == 'POST' and request.user.is_authenticated:
            ident = str(request.user.pk)
            if COMPLAINT_FILING.is_blocked(ident):
                return _too_many(request, 'You have filed a lot of complaints in the last hour. '
                                          'Please try again a little later.')
            response = view(request, *args, **kwargs)
            if response.status_code in (301, 302):  # a complaint was actually filed
                COMPLAINT_FILING.hit(ident)
            return response
        return view(request, *args, **kwargs)

    return wrapper
