# config/settings/__init__.py
#
# Loads the environment-appropriate settings module.
#
#   DJANGO_ENV=dev   → config.settings.dev
#   DJANGO_ENV=prod  → config.settings.prod
#
# Fail closed: with DJANGO_ENV unset, development settings are used only when
# DEBUG=True is explicitly configured. Anything else gets production settings,
# which refuse to start without a real SECRET_KEY and explicit ALLOWED_HOSTS —
# so a forgotten variable can never ship a debug-mode server.
from decouple import config

_ENV = config('DJANGO_ENV', default='').strip().lower()
if not _ENV:
    _ENV = 'dev' if config('DEBUG', default=False, cast=bool) else 'prod'

if _ENV in ('prod', 'production'):
    from .prod import *   # noqa: F401,F403
elif _ENV in ('dev', 'development', 'local'):
    from .dev import *    # noqa: F401,F403
else:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(f'Unknown DJANGO_ENV "{_ENV}". Use "dev" or "prod".')
