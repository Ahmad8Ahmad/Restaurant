"""Authentication for WebSocket connections.

The Channels AuthMiddlewareStack resolves the user from the Django session
cookie carried on the handshake.  Behind a proxy / multi-worker setup the
session cookie is not always forwarded to the WebSocket upgrade request, so
the connection is seen as anonymous and gets rejected with a 403.

This middleware adds two fallbacks, tried in order:

* ``sessionid`` query parameter — the page's own session id, for the case
  where the cookie is dropped on the upgrade.
* ``token`` query parameter — a SimpleJWT *access* token, which is what the
  Flutter app holds. The app is a pure JWT client with no Django session, so
  without this branch its sockets were always rejected as anonymous.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


@database_sync_to_async
def _load_session_user(session_key):
    from accounts.models import User
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.auth import SESSION_KEY, HASH_SESSION_KEY, BACKEND_SESSION_KEY

    if not session_key:
        return None
    try:
        store = SessionStore(session_key=session_key)
        data = store.load()
    except Exception:
        return None

    user_id = data.get(SESSION_KEY)
    if not user_id:
        return None
    try:
        user = User.objects.filter(pk=user_id).first()
    except Exception:
        return None
    if user is None or not user.is_active:
        return None
    return user


@database_sync_to_async
def _load_jwt_user(token):
    """Resolve a SimpleJWT access token to a user, or None if unusable."""
    from accounts.models import User

    if not token:
        return None
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
    except ImportError:
        return None

    try:
        validated = JWTAuthentication().get_validated_token(token)
    except Exception:
        # Expired, tampered or otherwise invalid: treat as anonymous rather
        # than letting the handshake fail with a 500.
        return None

    # SimpleJWT's Token subclasses dict, so the claim is a plain lookup.
    user_id = validated.get('user_id')
    if not user_id:
        return None

    try:
        user = User.objects.filter(pk=user_id).first()
    except Exception:
        return None
    if user is None or not user.is_active:
        return None
    return user


class WebSocketSessionAuthMiddleware(BaseMiddleware):
    """Authenticate a WebSocket from a sessionid or JWT query param."""

    async def __call__(self, scope, receive, send):
        user = scope.get('user')
        if user is None or not getattr(user, 'is_authenticated', False):
            query = parse_qs(scope.get('query_string', b'').decode('utf-8', 'ignore'))
            session_key = (query.get('sessionid') or [None])[0]
            resolved = await _load_session_user(session_key)
            if resolved is not None:
                scope['user'] = resolved
            else:
                token = (query.get('token') or [None])[0]
                resolved = await _load_jwt_user(token)
                if resolved is not None:
                    scope['user'] = resolved
        return await super().__call__(scope, receive, send)
