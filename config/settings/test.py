# config/settings/test.py
"""Settings for the test suite — fast, quiet, and isolated from real services."""
import tempfile

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, REST_FRAMEWORK

SECRET_KEY = 'test-only-secret-key-not-used-anywhere-else-0123456789'
DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost']

# WhiteNoise warns on every request that staticfiles/ has not been collected.
MIDDLEWARE = [m for m in MIDDLEWARE if 'whitenoise' not in m]

# MD5 instead of PBKDF2: deliberate key stretching is what you want in
# production and exactly what you do not want across ~90 tests.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# Uploaded files land in a temp dir that the OS cleans up, never in media/.
MEDIA_ROOT = tempfile.mkdtemp(prefix='nagriksetu-test-')
USE_OBJECT_STORAGE = False

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = ''

# Throttling would make test order significant. Rates stay defined because
# some views declare a scoped throttle and DRF needs a rate for every scope.
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    scope: '100000/day' for scope in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
}

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# Keep test output to the test results themselves.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
    'loggers': {
        'nagriksetu': {'handlers': ['null'], 'level': 'CRITICAL', 'propagate': False},
        'django.request': {'handlers': ['null'], 'level': 'CRITICAL', 'propagate': False},
    },
}
