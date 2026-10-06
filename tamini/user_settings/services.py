"""Firebase-backed account helpers shared by the website views and the API.

The Django views in ``user_settings.views`` (session auth, HTML) and the DRF
views in ``api.views.settings`` (JWT auth, JSON) must verify ownership and
delete the account in exactly the same way, so the logic lives here.
"""

import json
import logging
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings as django_settings

from accounts.models import PendingSignup

logger = logging.getLogger(__name__)

FIREBASE_FIRSTORE_SIGN_IN_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword'
FIREBASE_WEB_API_KEY = getattr(django_settings, 'FIREBASE_WEB_API_KEY', None) or 'AIzaSyDNLoORMEZ3Uc0YTu_iSrjTk5wIbgdpZOs'


def verify_firebase_password(email, password):
    """Re-verify credentials against Firebase Identity Toolkit (REST).

    Returns the Firebase uid (localId) on success, None.  Used to confirm
    that the person asking to delete an account still knows its password
    (Google/phone-only accounts cannot pass this check).
    """
    if not email or not password:
        return None
    payload = json.dumps({
        'email': email,
        'password': password,
        'returnSecureToken': True,
    }).encode('utf-8')
    url = f'{FIREBASE_FIRSTORE_SIGN_IN_URL}?key={FIREBASE_WEB_API_KEY}'
    req = Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        logger.info('Firebase password re-verification failed (HTTP %s)', exc.code)
        return None
    except Exception:
        logger.exception('Firebase password re-verification: unexpected network error')
        return None
    return (data.get('localId') or '').strip() or None


def verify_firebase_id_token(id_token):
    """Verify a fresh Firebase ID token (after client-side reauthentication).

    Returns the decoded token dict on success, None.  Used for
    Google/phone-only accounts that have no password to re-enter.
    """
    from tamini.firebase import initialize_firebase
    initialize_firebase()
    import firebase_admin
    if not firebase_admin._apps:
        logger.warning('Cannot verify ID token: Firebase Admin SDK not initialized')
        return None
    from firebase_admin import auth as fb_auth
    try:
        return fb_auth.verify_id_token(id_token, check_revoked=True)
    except fb_auth.InvalidIdTokenError as exc:
        logger.info('verify_firebase_id_token: rejected id_token: %s', exc)
        return None
    except Exception:
        logger.exception('verify_firebase_id_token: unexpected id_token verification failure')
        return None


def delete_firebase_user(firebase_uid):
    if not firebase_uid:
        return
    from tamini.firebase import initialize_firebase
    initialize_firebase()
    import firebase_admin
    if not firebase_admin._apps:
        logger.warning('Firebase Admin SDK not initialized, cannot delete user %s', firebase_uid)
        return
    from firebase_admin import auth as fb_auth
    try:
        fb_auth.delete_user(firebase_uid)
    except fb_auth.UserNotFoundError:
        logger.info('Firebase user %s already deleted', firebase_uid)


def delete_user_account(user):
    """Hard-delete: Firebase user, pending signups, then the DB row."""
    delete_firebase_user(user.firebase_uid)

    PendingSignup.objects.filter(email__iexact=user.email).delete()
    if user.phone:
        PendingSignup.objects.filter(phone=user.phone).delete()

    user.delete()


def match_firebase_uid(user, decoded):
    """True when a verified Firebase token really belongs to ``user``.

    Handles both linked accounts (``firebase_uid``) and legacy rows that were
    only matched by email.
    """
    uid = decoded['uid']
    if user.firebase_uid and uid != user.firebase_uid:
        return False
    if not user.firebase_uid:
        token_email = (decoded.get('email') or '').strip().lower()
        if token_email and token_email != (user.email or '').strip().lower():
            return False
    return True
