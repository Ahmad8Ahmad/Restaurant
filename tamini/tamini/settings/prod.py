from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*', 'localhost', '127.0.0.1'])

# Production MUST use Postgres. Fail loudly instead of silently degrading
# to SQLite (SQLite breaks under concurrent writes).
if not env('DATABASE_URL', default='').startswith(('postgres://', 'postgresql://')):
    raise ImproperlyConfigured(
        'DATABASE_URL must point to a PostgreSQL database in production.'
    )
try:
    import psycopg2  # noqa: F401
except ImportError:
    raise ImproperlyConfigured(
        'psycopg2 is required in production (pip install psycopg2-binary).'
    )
DATABASES = {
    'default': env.db('DATABASE_URL'),
}

# Pools DB connections — important under the multi-worker gunicorn setup.
# Set DATABASE_CONN_MAX_AGE on the server (e.g. 60) for keep-alive connections.
DATABASES['default']['CONN_MAX_AGE'] = env.int('DATABASE_CONN_MAX_AGE', default=60)

try:
    import cloudinary_storage
    INSTALLED_APPS += ['cloudinary_storage', 'cloudinary']
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': env('CLOUDINARY_CLOUD_NAME', default=''),
        'API_KEY': env('CLOUDINARY_API_KEY', default=''),
        'API_SECRET': env('CLOUDINARY_API_SECRET', default=''),
    }
    if CLOUDINARY_STORAGE['CLOUD_NAME']:
        STORAGES['default']['BACKEND'] = 'cloudinary_storage.storage.MediaCloudinaryStorage'
except ImportError:
    pass

SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
SECURE_BROWSER_XSS_FILTER = env.bool('SECURE_BROWSER_XSS_FILTER', default=True)
SECURE_CONTENT_TYPE_NOSNIFF = env.bool('SECURE_CONTENT_TYPE_NOSNIFF', default=True)
X_FRAME_OPTIONS = env('X_FRAME_OPTIONS', default='DENY')
