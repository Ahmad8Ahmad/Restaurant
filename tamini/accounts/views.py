import json
import logging
import random
import hashlib
import datetime
import uuid

from django.conf import settings
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from tamini.utils import send_mail_async
from django.template.loader import render_to_string
from .models import User
from .forms import UserRegistrationForm
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.utils import timezone
from restaurants.models import Restaurant
from delivery.models import DriverProfile
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class _LoginError(Exception):
    """Raised by login helpers to signal a client-facing error response."""

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


@csrf_exempt
@require_POST
@ratelimit(key='ip', rate='10/m', method='POST')
def firebase_session_login(request):
    """Accept a Firebase ID token via AJAX, verify it, and log the user
    in with a Django session.  Returns JSON so the frontend JS can
    redirect on success.

    CSRF is intentionally exempt: the Firebase ID token provides
    cryptographic authentication on every request.
    """
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many attempts. Please try again later.'}, status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    id_token = (body.get('id_token') or '').strip()
    if not id_token:
        return JsonResponse({'error': 'id_token is required'}, status=400)

    from tamini.firebase import initialize_firebase
    initialize_firebase()

    import firebase_admin
    if not firebase_admin._apps:
        logger.error(
            'Firebase session login unavailable: Admin SDK not initialized '
            '(missing FIREBASE_CREDENTIALS / FIREBASE_CREDENTIALS_FILE).'
        )
        return JsonResponse({'error': 'Server authentication not configured'}, status=503)

    from firebase_admin import auth as fb_auth
    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
    except fb_auth.InvalidIdTokenError as exc:
        # Covers invalid, expired, and revoked tokens — the client's fault.
        logger.info('Firebase session login rejected a token: %s', exc)
        return JsonResponse({'error': 'Invalid or expired token'}, status=401)
    except Exception:
        # Anything else (network to Google cert endpoint, misconfiguration,
        # clock skew) is a server-side problem, not a bad token.
        logger.exception('Firebase session login: unexpected verify failure')
        return JsonResponse({'error': 'Authentication service temporarily unavailable'}, status=503)

    firebase_uid = decoded['uid']
    email = decoded.get('email')
    phone = decoded.get('phone_number')

    if not email and not phone:
        return JsonResponse({'error': 'Token must contain email or phone'}, status=400)

    # Email sign-ups must confirm their address before a Django session is
    # created.  Phone-number tokens are already verified by SMS.
    if email and not decoded.get('email_verified'):
        logger.info('Firebase session login rejected unverified email for uid %s', firebase_uid)
        return JsonResponse({
            'error': _('يرجى تأكيد بريدك الإلكتروني قبل المتابعة.'),
            'code': 'email_not_verified',
        }, status=403)

    # get-or-create user.  Identity comes ONLY from the verified token:
    # the request body's 'phone' is profile data and must never be used
    # to look up a user, or anyone could take over an account by posting
    # someone else's number alongside their own token.
    try:
        user, created = _get_or_create_user(decoded, body)
    except _LoginError as exc:
        payload = {'error': exc.message}
        if exc.code:
            payload['code'] = exc.code
        return JsonResponse(payload, status=exc.status)
    except Exception:
        logger.exception('Firebase session login: unexpected error during user lookup/create')
        return JsonResponse({'error': 'Something went wrong. Please try again.'}, status=500)

    # Multiple auth backends are configured, so Django requires an explicit
    # backend when logging in a user that was not obtained via authenticate().
    try:
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    except Exception:
        logger.exception('Firebase session login: unexpected error during session creation')
        return JsonResponse({'error': 'Something went wrong. Please try again.'}, status=500)

    return JsonResponse({
        'ok': True,
        'created': created,
        'redirect': _get_login_redirect(user),
    })


def _get_or_create_user(decoded, body):
    """Get or create the Django user from a verified Firebase token.

    Returns a (user, created) tuple.  Raises _LoginError for client-facing
    rejections and any other Exception for internal database failures.
    """
    firebase_uid = decoded['uid']
    email = decoded.get('email')
    phone = decoded.get('phone_number')
    display_name = decoded.get('name', '')
    extra_role = (body.get('role') or '').strip()
    extra_phone = (body.get('phone') or '').strip()
    extra_address = (body.get('address') or '').strip()

    user = None
    if email:
        user = User.objects.filter(email=email).first()
    if user is None and phone:
        user = User.objects.filter(phone=phone).first()

    created = False
    if user is None:
        username_base = (email or phone or extra_phone).split('@')[0] if email else f'user_{(phone or extra_phone)[-4:]}'
        username = f'{username_base}_{uuid.uuid4().hex[:8]}'
        for _attempt in range(5):
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email or f'{firebase_uid}@firebase.local',
                        phone=phone or extra_phone or '',
                        first_name=display_name,
                        address=extra_address or '',
                        is_active=True,
                        is_verified=True,
                        firebase_uid=firebase_uid,
                    )
                    SAFE_SIGNUP_ROLES = ('customer', 'restaurant', 'delivery')
                    if extra_role in SAFE_SIGNUP_ROLES:
                        user.role = extra_role
                        user.save(update_fields=['role'])
                    created = True

                    if user.role == 'restaurant':
                        Restaurant.objects.get_or_create(
                            owner=user, defaults={'name': f'Restaurant of {user.username}', 'is_approved': False}
                        )
                    elif user.role == 'delivery':
                        DriverProfile.objects.get_or_create(user=user, defaults={'is_approved': False})
                break
            except IntegrityError:
                username = f'{username_base}_{uuid.uuid4().hex[:8]}'
    else:
        # Reject if another user already owns this Firebase UID.
        if user.firebase_uid and user.firebase_uid != firebase_uid:
            raise _LoginError(
                _('This email is already linked to another account.'),
                status=409, code='uid_conflict',
            )

        # Reject login for deactivated (banned) users.
        if not user.is_active:
            raise _LoginError(
                _('This account has been deactivated.'),
                status=403, code='account_deactivated',
            )

        # Before linking, ensure no other user already has this UID.
        if not user.firebase_uid and User.objects.filter(firebase_uid=firebase_uid).exclude(pk=user.pk).exists():
            raise _LoginError(
                _('This Firebase account is already linked to another user.'),
                status=409, code='uid_conflict',
            )

        changed = False
        if not user.firebase_uid:
            user.firebase_uid = firebase_uid
            changed = True
        if not user.is_verified:
            user.is_verified = True
            changed = True
        if phone and not user.phone:
            user.phone = phone
            changed = True
        if changed:
            user.save(update_fields=['firebase_uid', 'is_verified', 'phone'])

    return user, created


def _get_login_redirect(user):
    if user.role == 'restaurant':
        return '/restaurants/dashboard/'
    elif user.role == 'delivery':
        return '/delivery/available/'
    return '/'

@ratelimit(key='ip', rate='10/m', method='POST')
def register(request):
    return render(request, 'accounts/register.html')

@ratelimit(key='ip', rate='10/m', method='POST')
def verify_otp(request):
    """Deprecated — verification now uses Firebase only."""
    from django.http import HttpResponseGone
    return HttpResponseGone('OTP verification is no longer supported. Please use Firebase sign-in.')

@ratelimit(key='ip', rate='3/m', method='POST')
def resend_otp(request):
    """Deprecated — verification now uses Firebase only."""
    from django.http import HttpResponseGone
    return HttpResponseGone('OTP verification is no longer supported. Please use Firebase sign-in.')


@login_required
def login_success(request):
    if request.user.role == 'restaurant':
        return redirect('restaurants:restaurant_dashboard')
    elif request.user.role == 'delivery':
        # التوجيه لصفحة الطلبات المتاحة بدلاً من داشبورد طلب محدد
        return redirect('delivery:available_orders') 
    else:
        return redirect('home')


def verification_success(request):
    """Landing page Firebase redirects to after the user clicks the
    email-verification link (ActionCodeSettings.continueUrl).  The page
    polls Firebase, and once the address is verified it logs the user
    in via firebase_session_login and forwards them into the site.
    """
    return render(request, 'accounts/verification_success.html')
            
   
   
       
    

