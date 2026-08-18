"""Firebase Cloud Messaging helper.

Sending is a silent no-op when Firebase credentials are not configured, so the
rest of the app keeps working in local development.
Configure one of:
  - FCM_CREDENTIALS_JSON      raw service-account JSON
  - FCM_SERVICE_ACCOUNT_JSON  path to a service-account JSON file
  - GOOGLE_APPLICATION_CREDENTIALS (standard GCP env var)
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_app = None
_ready = False


def _get_app():
    global _app, _ready
    if _ready:
        return _app
    _ready = True
    try:
        import firebase_admin
        from firebase_admin import credentials

        raw = os.environ.get('FCM_CREDENTIALS_JSON')
        path = os.environ.get('FCM_SERVICE_ACCOUNT_JSON') or os.environ.get(
            'GOOGLE_APPLICATION_CREDENTIALS'
        )
        if raw:
            try:
                info = json.loads(raw)
                cred = credentials.Certificate(info)
            except Exception as exc:  # pragma: no cover - config dependent
                logger.warning('FCM: invalid FCM_CREDENTIALS_JSON: %s', exc)
                return None
        elif path and os.path.exists(path):
            try:
                cred = credentials.Certificate(path)
            except Exception as exc:  # pragma: no cover - config dependent
                logger.warning('FCM: invalid service account file: %s', exc)
                return None
        else:
            logger.info('FCM: no credentials configured, push disabled.')
            return None
        _app = firebase_admin.initialize_app(cred)
        logger.info('FCM: initialized.')
    except Exception as exc:  # pragma: no cover - import/config dependent
        logger.warning('FCM: disabled (%s)', exc)
    return _app


def send_to_tokens(tokens, title, body, data=None):
    """Send a notification to an iterable of FCM device tokens."""
    app = _get_app()
    if app is None:
        return 0
    tokens = [t for t in set(tokens) if t]
    if not tokens:
        return 0
    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in (data or {}).items()},
        )
        response = messaging.send_each_for_multicast(message, app=app)
        failed = sum(1 for r in response.responses if not r.success)
        if failed:
            logger.info('FCM: %s ok, %s failed', len(tokens) - failed, failed)
        return len(tokens) - failed
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning('FCM: send failed: %s', exc)
        return 0


def send_to_user(user, title, body, data=None):
    """Send a notification to every device registered for a user."""
    if user is None:
        return 0
    try:
        tokens = list(
            user.fcm_devices.values_list('token', flat=True).distinct()
        )
    except Exception as exc:  # pragma: no cover
        logger.warning('FCM: token lookup failed: %s', exc)
        return 0
    return send_to_tokens(tokens, title, body, data)


def send_to_role(role, title, body, data=None):
    """Send a notification to all users of a given role."""
    from accounts.models import User

    try:
        tokens = list(
            User.objects.filter(role=role, is_active=True)
            .values_list('fcm_devices__token', flat=True)
            .distinct()
        )
    except Exception as exc:  # pragma: no cover
        logger.warning('FCM: role lookup failed: %s', exc)
        return 0
    return send_to_tokens(tokens, title, body, data)
