# config/settings/base.py
"""
Settings shared by every environment.

Environment-specific overrides live in dev.py / prod.py / test.py and are
selected by DJANGO_ENV (see config/settings/__init__.py). Every value comes
from the environment via python-decouple; see .env.example.
"""
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config
from django.utils.csp import CSP

# BASE_DIR points at the repository root (three parents up from this file).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

APP_VERSION = '2.1.0'

# ── Security ──────────────────────────────────────────────
# No default here on purpose: dev.py supplies a throwaway key, prod.py refuses
# to start without a real one.
SECRET_KEY = config('SECRET_KEY', default='')
DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())
# Rate limiting keys on the client address; only trust X-Forwarded-For behind a proxy.
TRUST_X_FORWARDED_FOR = config('TRUST_X_FORWARDED_FOR', default=False, cast=bool)

# ── Apps ──────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    'corsheaders',
]

LOCAL_APPS = [
    'core',
    'users',
    'complaints',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'core.middleware.RequestLogMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.csp',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ── Database ──────────────────────────────────────────────
DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True),
}

# ── Cache ─────────────────────────────────────────────────
# Used by the login/filing rate limiter. Redis makes limits shared across
# workers; without it each process counts on its own.
REDIS_URL = config('REDIS_URL', default='')
CACHES = {
    'default': (
        {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': REDIS_URL}
        if REDIS_URL else
        {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    ),
}

# ── Auth ──────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/users/login/'

# ── Internationalization ───────────────────────────────────
LANGUAGE_CODE = 'en-in'
TIME_ZONE = config('TIME_ZONE', default='Asia/Kolkata')
USE_I18N = True
USE_TZ = True

# ── Static & media ────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Uploaded photos go to S3-compatible object storage (AWS S3, Cloudflare R2,
# MinIO…) when a bucket is configured, and to MEDIA_ROOT otherwise.
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
USE_OBJECT_STORAGE = bool(AWS_STORAGE_BUCKET_NAME)
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='')

if USE_OBJECT_STORAGE:
    _media_storage = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': AWS_STORAGE_BUCKET_NAME,
            'access_key': config('AWS_ACCESS_KEY_ID', default=''),
            'secret_key': config('AWS_SECRET_ACCESS_KEY', default=''),
            'endpoint_url': AWS_S3_ENDPOINT_URL or None,
            'region_name': config('AWS_S3_REGION_NAME', default='auto'),
            'custom_domain': AWS_S3_CUSTOM_DOMAIN or None,
            # Private buckets get short-lived signed URLs; a public custom domain does not need them.
            'querystring_auth': config('AWS_QUERYSTRING_AUTH', default=not AWS_S3_CUSTOM_DOMAIN, cast=bool),
            'file_overwrite': False,
            'default_acl': None,
        },
    }
else:
    _media_storage = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}

STORAGES = {
    'default': _media_storage,
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# Serve MEDIA_ROOT from Django itself outside DEBUG. Only for single-instance
# demos without object storage — files on an ephemeral disk vanish on redeploy.
SERVE_MEDIA_FROM_APP = config('SERVE_MEDIA_FROM_APP', default=False, cast=bool)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Uploads ───────────────────────────────────────────────
# Enforced for both the web form and the API by complaints.rules.validate_photo.
MAX_UPLOAD_SIZE_MB = config('MAX_UPLOAD_SIZE_MB', default=8, cast=int)
IMAGE_MAX_PIXELS = config('IMAGE_MAX_PIXELS', default=40_000_000, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024       # non-file form fields
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024       # larger uploads spool to disk

# Image pipeline tuning (see core/imaging.py).
IMAGE_MAX_WIDTH = config('IMAGE_MAX_WIDTH', default=1600, cast=int)
IMAGE_THUMBNAIL_WIDTH = config('IMAGE_THUMBNAIL_WIDTH', default=480, cast=int)
IMAGE_JPEG_QUALITY = config('IMAGE_JPEG_QUALITY', default=85, cast=int)

# ── DRF ───────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('THROTTLE_ANON', default='30/min'),
        'user': config('THROTTLE_USER', default='120/min'),
        'complaint-write': config('THROTTLE_COMPLAINT_WRITE', default='20/hour'),
        'login': config('THROTTLE_LOGIN', default='10/min'),
        'register': config('THROTTLE_REGISTER', default='10/hour'),
    },
    'EXCEPTION_HANDLER': 'core.exceptions.api_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_MINUTES', default=30, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    # A rotated or signed-out refresh token can never be used again.
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'NagrikSetu API',
    'DESCRIPTION': (
        'Civic grievance management — file geo-tagged complaints, move them through an audited '
        'workflow, and discuss them with the ward office.\n\n'
        '**Authentication.** `POST /api/auth/token/` with username and password returns a JWT pair. '
        'Send `Authorization: Bearer <access>`; rotate with `/api/auth/token/refresh/` and revoke with '
        '`/api/auth/logout/`. A signed-in browser session also works.\n\n'
        '**Roles.** Citizens file and track complaints and can support ones in their ward. '
        'Corporators triage and resolve complaints in their ward (or city-wide if they have no ward).\n\n'
        '**Errors** always look like `{"detail": "...", "code": "...", "errors": {...}}` — `errors` '
        'is present only for validation failures.'
    ),
    'VERSION': APP_VERSION,
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'SWAGGER_UI_SETTINGS': {'persistAuthorization': True, 'displayRequestDuration': True},
    'TAGS': [
        {'name': 'auth', 'description': 'Registration, JWT tokens and your profile'},
        {'name': 'complaints', 'description': 'Complaints, workflow, comments and upvotes'},
        {'name': 'wards', 'description': 'Municipal wards'},
    ],
    # status, old_status and new_status share one choice set; naming it once
    # stops spectacular emitting StatusEnum/OldStatusEnum/…
    'ENUM_NAME_OVERRIDES': {
        'StatusEnum': 'complaints.models.Status.choices',
        'IssueTypeEnum': 'complaints.models.IssueType.choices',
        'PriorityEnum': 'complaints.models.Priority.choices',
        'EventKindEnum': 'complaints.models.EventKind.choices',
    },
}

# ── CORS ──────────────────────────────────────────────────
# Closed unless origins are listed explicitly.
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())
CORS_URLS_REGEX = r'^/api/.*$'
CORS_ALLOW_CREDENTIALS = config('CORS_ALLOW_CREDENTIALS', default=False, cast=bool)

# ── Content Security Policy (Django's built-in middleware) ─
_MEDIA_ORIGINS = [f'https://{AWS_S3_CUSTOM_DOMAIN}'] if AWS_S3_CUSTOM_DOMAIN else []
if USE_OBJECT_STORAGE and not AWS_S3_CUSTOM_DOMAIN:
    _MEDIA_ORIGINS.append(AWS_S3_ENDPOINT_URL or 'https://*.amazonaws.com')

SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.NONCE, 'https://unpkg.com'],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://unpkg.com'],
    'img-src': [CSP.SELF, 'data:', 'blob:', 'https://*.tile.openstreetmap.org', *_MEDIA_ORIGINS],
    'font-src': [CSP.SELF],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

# ── Celery (optional) ─────────────────────────────────────
# With no broker configured the image pipeline runs inline, so the project
# stays a plain `runserver` app until someone actually wants a worker.
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='')
CELERY_TASK_ALWAYS_EAGER = not bool(CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# ── Email ─────────────────────────────────────────────────
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='NagrikSetu <noreply@nagriksetu.local>')

# ── Site ──────────────────────────────────────────────────
SITE_NAME = 'NagrikSetu'
SITE_TAGLINE = 'Report civic issues. Track progress. Build accountable communities.'
SITE_URL = config('SITE_URL', default='http://localhost:8000')

# ── Logging ───────────────────────────────────────────────
LOG_LEVEL = config('LOG_LEVEL', default='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_id': {'()': 'core.logging.RequestIdFilter'},
    },
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} [{request_id}] {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['request_id'],
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'nagriksetu': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
