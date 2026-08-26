import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseServerError
from django.utils import translation

logger = logging.getLogger(__name__)


class StripSharedVaryMiddleware:
    """Scrub per-visitor headers from anonymous shared-cached pages.

    Shared pages are rendered once and served to every anonymous visitor, and
    the CSRF token they carry is shared too. ``CsrfViewMiddleware`` adds
    ``Vary: Cookie`` whenever it sets the ``csrftoken`` cookie, which would
    make browser/CDN caches store one entry per cookie value — exactly the
    per-visitor caching behaviour this site is trying to avoid. Placed before
    ``SessionMiddleware`` so its ``process_response`` runs last and sees the
    final headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get('X-Tamini-Shared') == '1':
            response.__delitem__('X-Tamini-Shared')
            vary = response.get('Vary', '')
            kept = [v.strip() for v in vary.split(',') if v.strip().lower() != 'cookie']
            if kept:
                response['Vary'] = ', '.join(kept)
            else:
                response.__delitem__('Vary')
        return response


class SkipSessionForAnonymousMiddleware:
    """Avoid touching ``request.session`` for visitors with no session cookie.

    Merely reading the session marks it "accessed", which makes
    SessionMiddleware add ``Vary: Cookie`` to every response — that gives each
    visitor their own page-cache entry and defeats shared caching. Anonymous
    users have nothing in the session (cart/order code is what writes to it),
    so short-circuit the lazy auth lookup with a plain ``AnonymousUser``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.SESSION_COOKIE_NAME not in request.COOKIES:
            request.user = AnonymousUser()
        return self.get_response(request)


class ForceAdminEnglishMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            translation.activate('en')
            request.LANGUAGE_CODE = 'en'
        return self.get_response(request)


_REDIS_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def _is_redis_error(exc):
    """Return True if *exc* (or any cause) is a Redis connection error."""
    cur = exc
    for _ in range(10):
        if isinstance(cur, _REDIS_ERRORS):
            return True
        if cur.__cause__:
            cur = cur.__cause__
        elif cur.__context__:
            cur = cur.__context__
        else:
            break
    mod = type(cur).__module__ or ''
    name = type(cur).__qualname__
    if 'redis' in mod.lower() or 'redis' in name.lower():
        return True
    return False


class RedisFallbackMiddleware:
    """Catch Redis failures so a slow/down Redis does not500 every page.

    If SessionMiddleware or AuthenticationMiddleware raise a Redis error
    while reading the session or user, we log the failure and fall back
    to an anonymous request so the page can still be served.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as exc:
            if _is_redis_error(exc):
                logger.error("Redis unavailable, serving degraded response: %s", exc)
                if not hasattr(request, 'user') or request.user is None:
                    request.user = AnonymousUser()
                if not hasattr(request, 'session') or request.session is None:
                    from django.contrib.sessions.backends import cache as cache_sess
                    request.session = cache_sess.SessionStore()
                return self.get_response(request)
            raise
