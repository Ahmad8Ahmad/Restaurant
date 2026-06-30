import os
from pathlib import Path
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
        from .dev import *
else:
    from .dev import *
