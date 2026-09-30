# config/settings/dev.py
"""Local development settings — verbose and convenient, never for production."""
from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, SECRET_KEY, STORAGES

DEBUG = True

# A throwaway key so `runserver` works on a fresh clone.
SECRET_KEY = SECRET_KEY or 'django-insecure-local-development-only'

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', '0.0.0.0', '.localhost']

# Any localhost port may call the API while developing a mobile/SPA client.
CORS_ALLOWED_ORIGIN_REGEXES = [r'^http://(localhost|127\.0\.0\.1)(:\d+)?$']

# Throttling gets in the way of local testing.
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    scope: '1000/min' for scope in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
}

# Manifest storage requires a collectstatic run — unhelpful with runserver.
STORAGES = {
    **STORAGES,
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
