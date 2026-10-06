"""JSON counterparts of the website's /settings/ page.

The website renders ``user_settings`` with session auth and HTML forms; the
mobile app authenticates with a Bearer JWT, so it cannot reach those views.
These DRF views expose the same data and the same delete-account contract.
"""

import logging

from django.utils.translation import gettext as _
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from restaurants.models import SiteContent
from user_settings import services
from user_settings.models import UserPreference

from ..serializers import LegalContentSerializer, UserPreferenceSerializer

logger = logging.getLogger(__name__)

LEGAL_PAGES = {
    'terms': {
        'base': 'terms_of_service',
        'title': {'ar': 'شروط الخدمة', 'en': 'Terms of Service'},
    },
    'privacy': {
        'base': 'privacy_policy',
        'title': {'ar': 'سياسة الخصوصية', 'en': 'Privacy Policy'},
    },
}


def _resolve_language(request, query_lang):
    """ar/en from ?lang=, else the negotiated LANGUAGE_CODE, else ar."""
    lang = (query_lang or '').strip().lower()[:2]
    if lang in ('ar', 'en'):
        return lang
    negotiated = (getattr(request, 'LANGUAGE_CODE', '') or '').lower().split('-')[0]
    return negotiated if negotiated in ('ar', 'en') else 'ar'


class UserPreferenceView(APIView):
    """Read/update the caller's theme and notification toggles."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pref = UserPreference.get_or_create_for_user(request.user)
        return Response(UserPreferenceSerializer(pref).data)

    def put(self, request):
        return self._save(request, partial=False)

    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, partial):
        pref = UserPreference.get_or_create_for_user(request.user)
        serializer = UserPreferenceSerializer(pref, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DeleteAccountView(APIView):
    """Hard-delete the caller's account after proving ownership.

    Body (same contract as the website's /settings/delete-account/):
      - ``{"id_token": "<fresh firebase id token>"}`` — Google/phone accounts.
      - ``{"email": ..., "password": ...}`` — email/password accounts.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'delete-account'

    def post(self, request):
        user = request.user

        id_token = (request.data.get('id_token') or '').strip()
        if id_token:
            decoded = services.verify_firebase_id_token(id_token)
            if not decoded:
                return Response({
                    'ok': False,
                    'error': _('انتهت صلاحية التحقق، أعد التحقق من حسابك أولاً.'),
                }, status=status.HTTP_401_UNAUTHORIZED)
            uid = decoded['uid']
            if not services.match_firebase_uid(user, decoded):
                return Response(
                    {'ok': False, 'error': _('التحقق لا يخص هذا الحساب.')},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            email = (request.data.get('email') or '').strip().lower()
            password = request.data.get('password') or ''
            uid = services.verify_firebase_password(email, password)
            if not uid:
                return Response({
                    'ok': False,
                    'error': _('البريد أو كلمة المرور غير صحيحة، أو أن الحساب لا يستخدم كلمة مرور.'),
                }, status=status.HTTP_401_UNAUTHORIZED)
            if user.firebase_uid and uid != user.firebase_uid:
                return Response(
                    {'ok': False, 'error': _('البريد لا يخص هذا الحساب.')},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not user.firebase_uid and email != (user.email or '').strip().lower():
                return Response(
                    {'ok': False, 'error': _('البريد لا يخص هذا الحساب.')},
                    status=status.HTTP_403_FORBIDDEN,
                )

        services.delete_user_account(user)
        logger.info('api delete_account: id=%s firebase_uid=%s', user.pk, uid)
        return Response({'ok': True})


class LegalContentView(APIView):
    """Terms / privacy copy for the app: ``GET /api/legal/terms|privacy/``."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, page):
        meta = LEGAL_PAGES.get(page)
        if meta is None:
            return Response(
                {'detail': 'Unknown legal page.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        lang = _resolve_language(request, request.query_params.get('lang'))
        site_content = SiteContent.load()
        base = meta['base']
        content = (
            getattr(site_content, f'{base}_{lang}', '')
            or getattr(site_content, f'{base}_ar', '')
        )
        serializer = LegalContentSerializer({
            'slug': page,
            'title': meta['title'][lang],
            'content': content,
        })
        return Response(serializer.data)
