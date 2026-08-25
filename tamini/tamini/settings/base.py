import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / '.env'
if env_file.exists():
    env.read_env(str(env_file))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me-in-production')

DEBUG = env.bool('DEBUG', default=True)

SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN and not DEBUG:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.2,
        profiles_sample_rate=0.1,
        environment='production',
    )

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

INSTALLED_APPS = [
    'daphne',
    'modeltranslation',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'whitenoise.runserver_nostatic',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    # Apps
    'accounts',
    'restaurants.apps.RestaurantsConfig',
    'delivery.apps.DeliveryConfig',
    'payments',
    'orders.apps.OrdersConfig',
    'support.apps.SupportConfig',
    'anymail',
    # MUST be last so its signal handlers observe every model's files.
    'django_cleanup.apps.CleanupConfig',
]

MIDDLEWARE = [
    'tamini.middleware.StripSharedVaryMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'tamini.middleware.SkipSessionForAnonymousMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'tamini.middleware.ForceAdminEnglishMiddleware',
]

ROOT_URLCONF = 'tamini.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'tamini' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'support.context_processor.site_contact_processor',
                'tamini.context_processors.site_content',
            ],
        },
    },
]

WSGI_APPLICATION = 'tamini.wsgi.application'
ASGI_APPLICATION = 'tamini.asgi.application'

DATABASES = {
    'default': env.db_url('DATABASE_URL'),
}

REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379')

_redis_available = False
try:
    import redis as _redis
    _r = _redis.from_url(REDIS_URL)
    _r.ping()
    _r.connection_pool.disconnect()
    _redis_available = True
except Exception:
    pass

if _redis_available:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        },
    }
    # Keep sessions in Redis: fast, and no per-visitor DB writes (the
    # geolocation beacon would otherwise write a session row every visit).
    # Falls back to DB sessions when Redis is down (cache would be locmem,
    # which isn't shared across workers).
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        },
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

if _redis_available:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
    import logging
    logging.getLogger(__name__).warning('Redis unavailable. Falling back to InMemoryChannelLayer. WebSocket messages will not persist across process restarts.')

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ar'

LANGUAGES = [
    ('ar', 'العربية'),
    ('en', 'English'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'Asia/Damascus'

USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# WhiteNoise serves pre-compressed (.gz) copies of static files. A day-long
# max-age is a safe default since CSS is cache-busted with ?v= query strings.
WHITENOISE_MAX_AGE = 86400
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
AUTH_USER_MODEL = 'accounts.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Image upload optimization (tamini/media.py)
IMAGE_MAX_DIMENSION = env.int('IMAGE_MAX_DIMENSION', default=1000)
IMAGE_WEBP_QUALITY = env.int('IMAGE_WEBP_QUALITY', default=80)

LOGIN_URL = 'login'
DELIVERY_FEE = 5000
LOGIN_REDIRECT_URL = 'accounts:login_success'

SITE_CONTACT_EMAIL = env('EMAIL_USER', default='taminyfood@gmail.com')
SITE_CONTACT_PHONE = env('CONTACT_PHONE', default='+963 900 000 000')
SITE_WHATSAPP = env('WHATSAPP_NUMBER', default='963900000000')
SITE_INSTAGRAM = env('INSTAGRAM', default='https://instagram.com/taminy')
SITE_FACEBOOK = env('FACEBOOK', default='https://facebook.com/taminy')

EMAIL_HOST_USER = env('EMAIL_USER', default='taminyfood@gmail.com')
email_host_password = env('EMAIL_PASSWORD', default='')
mailgun_api_key = env('MAILGUN_API_KEY', default='')
mailgun_domain = env('MAILGUN_DOMAIN', default='')

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

if mailgun_api_key and mailgun_domain:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
    ANYMAIL = {
        'MAILGUN_API_KEY': mailgun_api_key,
        'MAILGUN_SENDER_DOMAIN': mailgun_domain,
    }
elif email_host_password:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_PASSWORD = email_host_password
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

import sys
print(f'[EMAIL DEBUG] Backend: {EMAIL_BACKEND} | PWD set: {bool(email_host_password)} | Mailgun: {bool(mailgun_api_key)}/{bool(mailgun_domain)}', file=sys.stderr)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_FAILURE_VIEW = 'tamini.views.csrf_failure'

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

GOOGLE_MAPS_API_KEY = env('GOOGLE_MAPS_API_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'detailed': {
            'format': '[{asctime}] {levelname:<8} {name:<20} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'errors.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'delay': True,
            'formatter': 'detailed',
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'debug.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'delay': True,
            'formatter': 'detailed',
        },
    },
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_error'],
            'level': 'WARNING',
            'propagate': False,
        },
        'orders': {
            'level': 'INFO',
        },
        'payments': {
            'level': 'INFO',
        },
        'support': {
            'level': 'INFO',
        },
        'restaurants': {
            'level': 'INFO',
        },
        'delivery': {
            'level': 'INFO',
        },
        'accounts': {
            'level': 'INFO',
        },
        'stripe': {
            'level': 'WARNING',
        },
        'channels': {
            'level': 'WARNING',
        },
    },
}

# ── Django REST Framework ──────────────────────────────────────────────
from datetime import timedelta

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '120/minute',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'TOKEN_OBTAIN_SERIALIZER': 'api.serializers.CustomTokenObtainSerializer',
}

# ── CORS ────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# ── drf-spectacular ────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'Tamini API',
    'DESCRIPTION': 'Food delivery platform API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
