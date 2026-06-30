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
    'accounts',
    'restaurants',
    'delivery.apps.DeliveryConfig',
    'payments',
    'orders.apps.OrdersConfig',
    'support.apps.SupportConfig',
    'anymail',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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
                'orders.context_processor.cart_count_processor',
                'support.context_processor.site_contact_processor',
                'tamini.context_processors.site_content',
            ],
        },
    },
]

WSGI_APPLICATION = 'tamini.wsgi.application'
ASGI_APPLICATION = 'tamini.asgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3'),
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
}

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
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
AUTH_USER_MODEL = 'accounts.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

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

LOGIN_URL = 'login'
DELIVERY_FEE = 5000
LOGIN_REDIRECT_URL = 'accounts:login_success'

SITE_CONTACT_EMAIL = env('EMAIL_USER', default='taminyfood@gmail.com')
SITE_CONTACT_PHONE = env('CONTACT_PHONE', default='+963 900 000 000')
SITE_WHATSAPP = env('WHATSAPP_NUMBER', default='963900000000')
SITE_INSTAGRAM = env('INSTAGRAM', default='https://instagram.com/taminy')
SITE_FACEBOOK = env('FACEBOOK', default='https://facebook.com/taminy')

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = env('EMAIL_USER')
    EMAIL_HOST_PASSWORD = env('EMAIL_PASSWORD')
    DEFAULT_FROM_EMAIL = env('EMAIL_USER', default='taminyfood@gmail.com')
else:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
    DEFAULT_FROM_EMAIL = env('EMAIL_USER', default='taminyfood@gmail.com')
    ANYMAIL = {
        'MAILGUN_API_KEY': env('MAILGUN_API_KEY'),
        'MAILGUN_SENDER_DOMAIN': env('MAILGUN_DOMAIN'),
    }

CSRF_FAILURE_VIEW = 'tamini.views.csrf_failure'

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

GOOGLE_MAPS_API_KEY = env('GOOGLE_MAPS_API_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')

LOG_DIR = BASE_DIR / 'logs'

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
