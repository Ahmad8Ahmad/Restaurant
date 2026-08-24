import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from dotenv import load_dotenv

load_dotenv(os.path.join(Path(__file__).resolve().parent.parent.parent, '.env'))

import certifi
curl_ca = os.environ.get('CURL_CA_BUNDLE', '')
if not curl_ca or not os.path.exists(curl_ca):
    os.environ['CURL_CA_BUNDLE'] = certifi.where()
    os.environ['SSL_CERT_FILE'] = certifi.where()

database_url = os.environ.get('DATABASE_URL', '')

if database_url.startswith('postgres://') or database_url.startswith('postgresql://'):
    try:
        import psycopg2
        from .prod import *
    except ImportError:
        raise ImproperlyConfigured(
            'DATABASE_URL points to PostgreSQL but psycopg2 is not installed.'
        )
else:
    # Never fall back to SQLite silently: an empty local file makes it
    # look like all data was deleted.  Fail loudly instead.
    raise ImproperlyConfigured(
        'DATABASE_URL is missing or not a postgresql:// URL. '
        'Set it in .env to the Supabase connection string. '
        '(Tests use tamini.settings.dev explicitly.)'
    )
