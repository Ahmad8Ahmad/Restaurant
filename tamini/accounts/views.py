import logging
import sys

from django.conf import settings
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import User
from .forms import UserRegistrationForm
import random
import hashlib
import datetime
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.utils import timezone
from restaurants.models import Restaurant
from delivery.models import DriverProfile
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

@ratelimit(key='ip', rate='5/m', method='POST')
def register(request):
    print(f'[EMAIL] register view HIT method={request.method}', file=sys.stderr, flush=True)
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
            print(f'[EMAIL] Sending OTP to {user.email} via {settings.EMAIL_BACKEND}', file=sys.stderr, flush=True)
            try:
                sent = send_mail(
                    _('كود التحقق - طعميني'),
                    _('كود التحقق الخاص بك هو: %(otp)s') % {'otp': otp},
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                    html_message=html_message,
                )
                print(f'[EMAIL] send_mail returned {sent} for {user.email}', file=sys.stderr, flush=True)
            except Exception as e:
                print(f'[EMAIL] ERROR: {e}', file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc(file=sys.stderr)
            
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
                    error = _("انتهت صلاحية كود التحقق. يرجى إعادة التسجيل.")
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
            auth_login(request, user)
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
    try:
        send_mail(
            _('كود تحقق جديد - طعميني'),
            _('كود التحقق الجديد الخاص بك هو: %(otp)s') % {'otp': otp},
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
            html_message=html_message,
        )
    except Exception as e:
        logger.error(f"Failed to resend verification email to {user.email}: {e}", exc_info=True)

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
            
   
   
       
    

