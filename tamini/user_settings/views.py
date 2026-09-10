import json
import logging
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext as _
from django.conf import settings as django_settings
from django_ratelimit.decorators import ratelimit
from accounts.models import PendingSignup
from .models import UserPreference
from .forms import UserPreferenceForm, ProfileForm

logger = logging.getLogger(__name__)

FIREBASE_FIRSTORE_SIGN_IN_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword'
FIREBASE_WEB_API_KEY = getattr(django_settings, 'FIREBASE_WEB_API_KEY', None) or 'AIzaSyDNLoORMEZ3Uc0YTu_iSrjTk5wIbgdpZOs'


def _verify_firebase_password(email, password):
    """Re-verify credentials against Firebase Identity Toolkit (REST).

    Returns the Firebase uid (localId) on success, None otherwise.  Used to
    confirm that the person asking to delete an account still knows its
    password (Google/phone-only accounts cannot pass this check).
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


def _verify_firebase_id_token(id_token):
    """Verify a fresh Firebase ID token (after client-side reauth).

    Returns the decoded token dict on success, None otherwise.  Used for
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
        logger.info('delete_account: rejected id_token: %s', exc)
        return None
    except Exception:
        logger.exception('delete_account: unexpected id_token verification failure')
        return None


def _delete_firebase_user(firebase_uid):
    if not firebase_uid:
        return
    from tamini.firebase import initialize_firebase
    initialize_firebase()
    import firebase_admin
    if not firebase_admin._apps:
        logger.warning('Cannot delete Firebase user %s: Admin SDK not initialized', firebase_uid)
        return
    from firebase_admin import auth as fb_auth
    try:
        fb_auth.delete_user(firebase_uid)
    except fb_auth.UserNotFoundError:
        logger.info('Firebase user %s already deleted', firebase_uid)


def _delete_verified_account(request, user, uid):
    """Shared hard-delete: Firebase + DB + pending cleanup + session."""
    _delete_firebase_user(user.firebase_uid)

    PendingSignup.objects.filter(email__iexact=user.email).delete()
    if user.phone:
        PendingSignup.objects.filter(phone=user.phone).delete()

    user.delete()
    request.session.flush()
    logger.info('Deleted account id=%s firebase_uid=%s', user.pk, uid)
    return JsonResponse({'ok': True})


@login_required
@require_POST
@ratelimit(key='ip', rate='5/m', method='POST', block=False)
def delete_account(request):
    """Hard-delete the account from the DB and Firebase.

    Two proof-of-ownership options:
      - {email, password}: password re-verification against Firebase
        (email/password accounts).
      - {id_token}: fresh Firebase ID token obtained after client-side
        reauthentication (Google/phone-only accounts).
    """
    if getattr(request, 'limited', False):
        return JsonResponse({'ok': False, 'error': _('محاولات كثيرة، حاول لاحقاً.')}, status=429)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': _('بيانات غير صالحة.')}, status=400)

    user = request.user

    id_token = (data.get('id_token') or '').strip()
    if id_token:
        decoded = _verify_firebase_id_token(id_token)
        if not decoded:
            return JsonResponse({
                'ok': False,
                'error': _('انتهت صلاحية التحقق، أعد التحقق من حسابك أولاً.'),
            }, status=401)
        uid = decoded['uid']
        if user.firebase_uid and uid != user.firebase_uid:
            return JsonResponse({'ok': False, 'error': _('التحقق لا يخص هذا الحساب.')}, status=403)
        if not user.firebase_uid:
            token_email = (decoded.get('email') or '').strip().lower()
            if token_email and token_email != (user.email or '').strip().lower():
                return JsonResponse({'ok': False, 'error': _('التحقق لا يخص هذا الحساب.')}, status=403)
    else:
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        uid = _verify_firebase_password(email, password)
        if not uid:
            return JsonResponse({
                'ok': False,
                'error': _('البريد أو كلمة المرور غير صحيحة، أو أن الحساب لا يستخدم كلمة مرور.'),
            }, status=401)
        if user.firebase_uid and uid != user.firebase_uid:
            return JsonResponse({'ok': False, 'error': _('البريد لا يخص هذا الحساب.')}, status=403)
        if not user.firebase_uid and email != (user.email or '').strip().lower():
            return JsonResponse({'ok': False, 'error': _('البريد لا يخص هذا الحساب.')}, status=403)

    return _delete_verified_account(request, user, uid)


@login_required
def settings_view(request):
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    profile_form = ProfileForm(initial={
        'username': request.user.username,
        'email': request.user.email,
        'phone': request.user.phone or '',
        'address': request.user.address or '',
    })
    pref_form = UserPreferenceForm(instance=pref)

    if request.method == 'POST':
        section = request.POST.get('section', 'profile')

        if section == 'profile':
            profile_form = ProfileForm(request.POST)
            if profile_form.is_valid():
                request.user.username = profile_form.cleaned_data['username']
                request.user.phone = profile_form.cleaned_data['phone'] or None
                request.user.address = profile_form.cleaned_data['address'] or None
                request.user.save()
                messages.success(request, _('تم تحديث الملف الشخصي بنجاح'))
                return redirect('user_settings:settings')

        elif section == 'preferences':
            pref_form = UserPreferenceForm(request.POST, instance=pref)
            if pref_form.is_valid():
                pref_form.save()
                messages.success(request, _('تم تحديث التفضيلات بنجاح'))
                return redirect('user_settings:settings')

    ctx = {
        'profile_form': profile_form,
        'pref_form': pref_form,
        'pref': pref,
        'app_version': '1.0.0',
    }
    return render(request, 'user_settings/settings.html', ctx)


@require_POST
@csrf_exempt
def toggle_dark_mode(request):
    """AJAX endpoint to toggle dark mode without page reload."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    data = json.loads(request.body.decode('utf-8')) if request.body else {}
    new_theme = data.get('theme', 'light')
    if new_theme not in ('light', 'dark', 'system'):
        new_theme = 'light'
    pref.theme = new_theme
    pref.save(update_fields=['theme'])
    return JsonResponse({'ok': True, 'theme': pref.theme})


@require_POST
@csrf_exempt
def toggle_notification(request, key):
    """AJAX endpoint to toggle notification preferences."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    valid_keys = {
        'order_updates': 'notify_order_updates',
        'promotions': 'notify_promotions',
        'email': 'notify_email',
    }
    if key not in valid_keys:
        return JsonResponse({'ok': False}, status=400)
    field = valid_keys[key]
    setattr(pref, field, not getattr(pref, field))
    pref.save(update_fields=[field])
    return JsonResponse({'ok': True, key: getattr(pref, field)})
