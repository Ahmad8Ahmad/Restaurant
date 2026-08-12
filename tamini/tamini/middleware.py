from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils import translation


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
