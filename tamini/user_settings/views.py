import json
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext as _
from django_ratelimit.decorators import ratelimit
from . import services
from .models import UserPreference
from .forms import UserPreferenceForm, ProfileForm

logger = logging.getLogger(__name__)


def _delete_verified_account(request, user, uid):
    """Shared hard-delete: Firebase + DB + pending cleanup + session."""
    services.delete_user_account(user)
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
        decoded = services.verify_firebase_id_token(id_token)
        if not decoded:
            return JsonResponse({
                'ok': False,
                'error': _('انتهت صلاحية التحقق، أعد التحقق من حسابك أولاً.'),
            }, status=401)
        uid = decoded['uid']
        if not services.match_firebase_uid(user, decoded):
            return JsonResponse({'ok': False, 'error': _('التحقق لا يخص هذا الحساب.')}, status=403)
    else:
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        uid = services.verify_firebase_password(email, password)
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
    pref, _created = UserPreference.objects.get_or_create(user=request.user)
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
    pref, _created = UserPreference.objects.get_or_create(user=request.user)
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
    pref, _created = UserPreference.objects.get_or_create(user=request.user)
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
