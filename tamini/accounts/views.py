import json
import logging
import random
import hashlib
import datetime

from django.conf import settings
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


@csrf_exempt
@require_POST
def firebase_session_login(request):
    """Accept a Firebase ID token via AJAX, verify it, and log the user
    in with a Django session.  Returns JSON so the frontend JS can
    redirect on success.

    CSRF is intentionally exempt: the Firebase ID token provides
    cryptographic authentication on every request.
    """
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
        decoded = fb_auth.verify_id_token(id_token)
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
    display_name = decoded.get('name', '')

    if not email and not phone:
        return JsonResponse({'error': 'Token must contain email or phone'}, status=400)

    # Email sign-ups must confirm their address before a Django session is
    # created.  Phone-number tokens are already verified by SMS.
    if email and not decoded.get('email_verified'):
        logger.info('Firebase session login rejected unverified email for uid %s', firebase_uid)
        return JsonResponse({
            'error': 'يرجى تأكيد بريدك الإلكتروني قبل المتابعة.',
            'code': 'email_not_verified',
        }, status=403)

    # extra fields sent by the registration form (role, phone, address)
    extra_role = (body.get('role') or '').strip()
    extra_phone = (body.get('phone') or '').strip()
    extra_address = (body.get('address') or '').strip()

    # get-or-create user
    user = None
    if email:
        user = User.objects.filter(email=email).first()
    if user is None and (phone or extra_phone):
        user = User.objects.filter(phone=phone or extra_phone).first()

    created = False
    if user is None:
        username_base = (email or phone or extra_phone).split('@')[0] if email else f'user_{(phone or extra_phone)[-4:]}'
        username = f'{username_base}_{random.randint(1000, 9999)}'
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
        if extra_role and extra_role in dict(User.ROLE_CHOICES):
            user.role = extra_role
            user.save(update_fields=['role'])
        created = True

        # create linked profiles for restaurant / delivery roles
        if user.role == 'restaurant':
            from restaurants.models import Restaurant
            Restaurant.objects.get_or_create(
                owner=user, defaults={'name': f'Restaurant of {user.username}', 'is_approved': False}
            )
        elif user.role == 'delivery':
            from delivery.models import DriverProfile
            DriverProfile.objects.get_or_create(user=user, defaults={'is_approved': False})
    else:
        changed = False
        if not user.firebase_uid:
            user.firebase_uid = firebase_uid
            changed = True
        if not user.is_verified:
            user.is_verified = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if (phone or extra_phone) and not user.phone:
            user.phone = phone or extra_phone
            changed = True
        if changed:
            user.save(update_fields=['firebase_uid', 'is_verified', 'is_active', 'phone'])

    # Multiple auth backends are configured, so Django requires an explicit
    # backend when logging in a user that was not obtained via authenticate().
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({
        'ok': True,
        'created': created,
        'redirect': _get_login_redirect(user),
    })


def _get_login_redirect(user):
    if user.role == 'restaurant':
        return '/restaurants/dashboard/'
    elif user.role == 'delivery':
        return '/delivery/available/'
    return '/'

@ratelimit(key='ip', rate='5/m', method='POST')
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            email_prefix = user.email.split('@')[0]
            random_suffix = random.randint(1000, 9999)
            user.username = f"{email_prefix}_{random_suffix}"
            user.is_active = False
            
            # توليد كود من 6 أرقام
            otp = str(random.randint(100000, 999999))
            user.otp_code = hashlib.sha256(otp.encode()).hexdigest()
            user.otp_created_at = timezone.now()
            user.save()
            
            html_message = render_to_string('accounts/verification_email.html', {'otp': otp, 'email': user.email})
            send_mail_async(
                _('كود التحقق - طعميني'),
                _('كود التحقق الخاص بك هو: %(otp)s') % {'otp': otp},
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
            )
            
            request.session['verification_email'] = user.email
            return redirect('accounts:verify_otp')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

@ratelimit(key='ip', rate='10/m', method='POST')
def verify_otp(request):
    email = request.session.get('verification_email')
    if not email:
        return redirect('accounts:register')
    
    error = None
    success = request.session.pop('resend_success', None)
    error_from_resend = request.session.pop('resend_error', None)
    if error_from_resend:
        error = error_from_resend

    # منع إعادة المحاولة السريعة (rate limiting بالجلسة)
    last_attempt = request.session.get('otp_last_attempt')
    if last_attempt:
        try:
            last_dt = datetime.datetime.fromisoformat(last_attempt)
            if timezone.is_naive(last_dt):
                last_dt = timezone.make_aware(last_dt)
            elapsed = (timezone.now() - last_dt).total_seconds()
            if elapsed < 30:
                error = _("يرجى الانتظار %(seconds)s ثانية قبل إعادة المحاولة.") % {'seconds': int(30 - elapsed)}
                return render(request, 'accounts/verify_otp.html', {'error': error, 'success': success})
        except (ValueError, TypeError):
            pass
    
    if request.method == 'POST':
        user_otp = request.POST.get('otp', '').strip()
        request.session['otp_last_attempt'] = timezone.now().isoformat()
        
        # فك تشفير كل الأكواد المخزنة (لأننا نستخدم SHA256)
        hashed_input = hashlib.sha256(user_otp.encode()).hexdigest()
        users = User.objects.filter(email=email)
        user = None
        for u in users:
            if u.otp_code == hashed_input:
                user = u
                break
        
        if user:
            # التحقق من صلاحية الكود (10 دقائق)
            if user.otp_created_at:
                elapsed = (timezone.now() - user.otp_created_at).total_seconds()
                if elapsed > 600:
                    # Direct users to the resend flow — re-registering would
                    # create a duplicate inactive account with the same email.
                    error = _("انتهت صلاحية كود التحقق. يرجى طلب كود جديد.")
                    return render(request, 'accounts/verify_otp.html', {'error': error, 'success': success})
            
            user.is_active = True
            user.is_verified = True
            user.otp_code = None
            user.otp_created_at = None
            user.save()
            if 'otp_last_attempt' in request.session:
                del request.session['otp_last_attempt']
            if user.role == 'restaurant':
                Restaurant.objects.get_or_create(owner=user, defaults={'name': _("مطعم %(username)s") % {'username': user.username}, 'is_approved': False})
            elif user.role == 'delivery':
                DriverProfile.objects.get_or_create(user=user, defaults={'is_approved': False})
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('accounts:login_success')
        else:
            error = _("كود التحقق غير صحيح. يرجى المحاولة مرة أخرى.")
            
    return render(request, 'accounts/verify_otp.html', {'error': error, 'success': success})

@ratelimit(key='ip', rate='3/m', method='POST')
def resend_otp(request):
    email = request.session.get('verification_email')
    if not email:
        return redirect('accounts:register')

    last_resend = request.session.get('otp_resend_time')
    if last_resend:
        try:
            last_dt = datetime.datetime.fromisoformat(last_resend)
            if timezone.is_naive(last_dt):
                last_dt = timezone.make_aware(last_dt)
            elapsed = (timezone.now() - last_dt).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                request.session['resend_error'] = _("يرجى الانتظار %(seconds)s ثانية قبل إعادة الإرسال.") % {'seconds': remaining}
                return redirect('accounts:verify_otp')
        except (ValueError, TypeError):
            pass

    user = None
    for u in User.objects.filter(email=email, is_active=False):
        if u.otp_code is not None:
            user = u
            break

    if not user:
        return redirect('accounts:register')

    otp = str(random.randint(100000, 999999))
    user.otp_code = hashlib.sha256(otp.encode()).hexdigest()
    user.otp_created_at = timezone.now()
    user.save()

    html_message = render_to_string('accounts/verification_email.html', {'otp': otp, 'email': user.email})
    send_mail_async(
        _('كود تحقق جديد - طعميني'),
        _('كود التحقق الجديد الخاص بك هو: %(otp)s') % {'otp': otp},
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
    )

    request.session['otp_resend_time'] = timezone.now().isoformat()
    request.session['resend_success'] = _("تم إرسال كود تحقق جديد إلى بريدك الإلكتروني.")
    return redirect('accounts:verify_otp')


@login_required
def login_success(request):
    if request.user.role == 'restaurant':
        return redirect('restaurants:restaurant_dashboard')
    elif request.user.role == 'delivery':
        # التوجيه لصفحة الطلبات المتاحة بدلاً من داشبورد طلب محدد
        return redirect('delivery:available_orders') 
    else:
        return redirect('home')
            
   
   
       
    

