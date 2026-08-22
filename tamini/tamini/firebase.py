import json
import os
import logging

import firebase_admin
from firebase_admin import credentials

logger = logging.getLogger(__name__)

_initialized = False


def initialize_firebase():
    global _initialized
    if _initialized:
        return

    cred = None

    # 1. JSON string in env var (Render production)
    raw = os.environ.get('FIREBASE_CREDENTIALS', '')
    if raw:
        try:
            info = json.loads(raw)
            cred = credentials.Certificate(info)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error('FIREBASE_CREDENTIALS env var is not valid JSON: %s', exc)

    # 2. File path in env var (local dev)
    if cred is None:
        path = os.environ.get('FIREBASE_CREDENTIALS_FILE', '')
        if path and os.path.isfile(path):
            cred = credentials.Certificate(path)

    # 3. Default well-known location (local dev convenience)
    if cred is None:
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tamini-app-food-a798d-firebase-adminsdk-fbsvc-fccc27e323.json',
        )
        if os.path.isfile(default_path):
            cred = credentials.Certificate(default_path)

    if cred is None:
        logger.warning(
            'Firebase credentials not found. '
            'Set FIREBASE_CREDENTIALS (JSON) or FIREBASE_CREDENTIALS_FILE (path).'
        )
        return

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    _initialized = True
    logger.info('Firebase Admin SDK initialized.')
