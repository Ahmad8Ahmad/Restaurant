from django.shortcuts import render, redirect
from django.core.mail import send_mail
from .models import User
from .forms import UserRegistrationForm
import random
from django.contrib.auth.decorators import login_required
from restaurants.models import Restaurant

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False # الحساب بكون معطل لحين التأكيد
            
            # توليد كود من 6 أرقام
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.save()
            
            # إرسال الإيميل
            send_mail(
                'كود التحقق لموقع طعمني',
                f'أهلاً بك، كود التحقق الخاص بك هو: {otp}',
                'from@taminy.com',
                [user.email],
                fail_silently=False,
            )
            
            # حفظ الـ email في الجلسة عشان نستخدمه في صفحة التأكيد
            request.session['verification_email'] = user.email
            return redirect('accounts:verify_otp') # رح ننشئ هاد الرابط بالخطوة الجاية
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

def verify_otp(request):
    email = request.session.get('verification_email')
    if not email:
        return redirect('accounts:register')
    
    if request.method == 'POST':
        user_otp = request.POST.get('otp')
        user = User.objects.filter(email=email, otp_code=user_otp).first()
        
        if user:
            user.is_active = True # تفعيل الحساب
            user.is_verified = True # حقلنا الجديد
            user.otp_code = None # مسح الكود عشان ما يستخدم مرة ثانية
            user.save()
            if user.role == 'restaurant':
                Restaurant.objects.get_or_create(owner=user, defaults={'name': f"مطعم {user.username}"}, is_approved=False)
            return redirect('login') # حوله لصفحة الدخول
        else:
            # هنا ممكن تبعث رسالة خطأ إن الكود غلط
            print("الكود غلط يا حبيب")
            
    return render(request, 'accounts/verify_otp.html')

@login_required
def login_seccess(request):
    if request.user.role == 'restaurant':
        return redirect('restaurants:restaurant_dashboard')
    elif request.user.role == 'delivery':
        # التوجيه لصفحة الطلبات المتاحة بدلاً من داشبورد طلب محدد
        return redirect('delivery:available_orders') 
    else:
        return redirect('home')
            
   
   
       
    

