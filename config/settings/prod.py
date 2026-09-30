# config/settings/prod.py
"""Production settings — hardened transport, cookies and headers; refuses unsafe config."""
from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, REST_FRAMEWORK, SECRET_KEY

DEBUG = False

# ── Fail closed on unsafe configuration ───────────────────
_INSECURE_KEY_MARKERS = ('django-insecure', 'change-me', 'changeme', 'secret')
if len(SECRET_KEY) < 40 or any(marker in SECRET_KEY.lower() for marker in _INSECURE_KEY_MARKERS):
    raise ImproperlyConfigured(
        'SECRET_KEY is missing or insecure. Generate one with '
        '`python -c "import secrets; print(secrets.token_urlsafe(64))"`.'
    )
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must list the real hostnames in production (no "*").')

# Behind Render / nginx, which set X-Forwarded-For and X-Forwarded-Proto.
TRUST_X_FORWARDED_FOR = config('TRUST_X_FORWARDED_FOR', default=True, cast=bool)

# ── HTTPS / transport security ────────────────────────────
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']  # platform probes speak plain HTTP

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ── Cookies ───────────────────────────────────────────────
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the fetch() helper in static/js/app.js reads it
CSRF_COOKIE_SAMESITE = 'Lax'

# ── Headers ───────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# ── API ───────────────────────────────────────────────────
# No browsable HTML API in production — JSON only.
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]
