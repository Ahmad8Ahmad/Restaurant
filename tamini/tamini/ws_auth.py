"""Authentication for WebSocket connections.

The Channels AuthMiddlewareStack resolves the user from the Django session
cookie carried on the handshake.  Behind a proxy / multi-worker setup the
session cookie is not always forwarded to the WebSocket upgrade request, so
the connection is seen as anonymous and gets rejected with a 403.

This middleware adds a fallback: the client can pass its existing session id
via the `sessionid` query parameter (read from the same cookie already used
on the page).  We load that session and resolve its logged-in user, so
authenticated sockets work even when the cookie is dropped on the upgrade.
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


class WebSocketSessionAuthMiddleware(BaseMiddleware):
    """Authenticate the WebSocket from a `sessionid` query param as a fallback."""

    async def __call__(self, scope, receive, send):
        user = scope.get('user')
        if user is None or not getattr(user, 'is_authenticated', False):
            query = parse_qs(scope.get('query_string', b'').decode('utf-8', 'ignore'))
            session_key = (query.get('sessionid') or [None])[0]
            resolved = await _load_session_user(session_key)
            if resolved is not None:
                scope['user'] = resolved
        return await super().__call__(scope, receive, send)
