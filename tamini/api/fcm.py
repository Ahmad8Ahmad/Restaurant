"""Firebase Cloud Messaging helper.

Sending is a silent no-op when Firebase credentials are not configured, so the
rest of the app keeps working in local development.
Configure one of:
  - FIREBASE_CREDENTIALS       raw service-account JSON (shared with auth)
  - FIREBASE_CREDENTIALS_FILE  path to a service-account JSON file
"""
import logging

logger = logging.getLogger(__name__)

_app = None
_ready = False


def _get_app():
    global _app, _ready
    if _ready:
        return _app
    _ready = True
    try:
        from tamini.firebase import initialize_firebase
        import firebase_admin

        initialize_firebase()
        if not firebase_admin._apps:
            logger.info('FCM: no Firebase app available, push disabled.')
            return None
        _app = firebase_admin.get_app()
        logger.info('FCM: initialized (shared Firebase app).')
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
