import hashlib
from functools import wraps

from django.core.cache import cache
from django.utils.cache import patch_response_headers

_VERSION_KEY = 'shared_page_version'


def _copy_response(response):
    """Return an independent copy of a response.

    The same cached object is served to every visitor, and downstream
    middleware mutates responses (GZipMiddleware compresses content and sets
    headers in place). A copy shields the cached entry from those mutations,
    so one stored response correctly serves gzip and plain clients alike.
    """
    return response.__class__(
        content=response.content,
        status=response.status_code,
        headers=response.headers.copy(),
    )


def _current_version():
    try:
        return cache.get(_VERSION_KEY, 1)
    except Exception:
        return 1


def invalidate_shared_pages():
    """Bump the shared page-cache version so all cached pages go stale.

    Old entries expire naturally via their TTL, so we never need to scan the
    cache backend for keys to delete.
    """
    try:
        cache.set(_VERSION_KEY, _current_version() + 1, timeout=None)
    except Exception:
        pass


def cache_shared_anon(timeout, *, skip=None):
    """Cache a GET response for anonymous visitors under one shared key.

    Cached pages must look identical for every visitor, otherwise they would
    need a per-visitor cache entry (what ``vary_on_cookie`` did) and the cache
    would never actually be hit. So:

      * anonymous users share a single cache entry per URL;
      * authenticated users always render fresh (their navbar/cart differ);
      * ``skip(request)`` can opt specific requests out (e.g. the location
        aware "nearby" sort which depends on session coordinates).

    The key is built from the full request path — i18n_patterns URLs already
    carry the language prefix, and the query string carries search/paging —
    and is versioned so content edits invalidate instantly.

    Only the uncompressed response is stored; ``GZipMiddleware`` compresses a
    fresh copy for each visitor at delivery time, so one entry serves both
    gzip and non-gzip clients.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, 'user', None)
            if user is not None and user.is_authenticated:
                return view_func(request, *args, **kwargs)
            if request.method != 'GET':
                return view_func(request, *args, **kwargs)
            if skip is not None and skip(request):
                return view_func(request, *args, **kwargs)

            key = 'shared_page:%s:%s' % (
                _current_version(),
                hashlib.sha1(request.get_full_path().encode('utf-8')).hexdigest(),
            )

            response = cache.get(key)
            if response is not None:
                return _copy_response(response)

            response = view_func(request, *args, **kwargs)
            if response.status_code == 200 and not response.streaming:
                patch_response_headers(response, timeout)
                # Mark the response as shared so a middleware can scrub
                # per-visitor headers (Vary: Cookie from the CSRF cookie)
                # before they reach the client or are cached downstream.
                response['X-Tamini-Shared'] = '1'
                cache.set(key, response, timeout)
            return _copy_response(response)

        return _wrapped

    return decorator
