from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            # Load tests hammer the SQLite file with concurrent writers;
            # raise the busy-wait timeout so requests queue instead of
            # failing with "database is locked".
            'timeout': 60,
        },
    }
}

# Using SMTP from base.py for real email delivery

CSRF_TRUSTED_ORIGINS = [
    'http://192.168.1.140',
    'http://192.168.1.140:8000',
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
