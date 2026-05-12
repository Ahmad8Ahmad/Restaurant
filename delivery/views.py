from django.shortcuts import get_object_or_404, redirect, render
from delivery.models import Delivery
from django.contrib.auth.decorators import login_required

from orders.models import Order

@login_required
def delivery_dashboard(request, order_id):
    deliveries = Delivery.objects.filter(order_id=order_id, delivery_person=request.user)
    return render(request, 'delivery/deliver_dashboard.html', {'deliveries': deliveries})

@login_required
def delivery_detail(request, delivery_id):
    delivery = get_object_or_404(Delivery, id=delivery_id, delivery_person=request.user)
    return render(request, 'delivery/detail.html', {'delivery': delivery})

def track_delivery(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # التحقق من الأمان:
    # 1. هل الشخص مسجل دخول وهو صاحب الطلب؟
    # 2. أو هل هو زائر "Guest" ومعه رقم الطلب في الـ session؟
    is_owner = False
    
    if request.user.is_authenticated and order.customer == request.user:
        is_owner = True
    elif request.session.get('placed_order_id') == order.id:
        is_owner = True

    if not is_owner:
        # إذا مو هو صاحب الطلب، نرجعه لصفحة تانية أو نعطيه خطأ
        return render(request, '403.html', {'message': 'عذراً، لا يمكنك تتبع هذا الطلب.'}, status=403)

    # إذا تأكدنا إنه صاحب الطلب، نكمل الشغل
    delivery, created = Delivery.objects.get_or_create(
        order=order, 
        defaults={'current_lat': 0, 'current_lng': 0}
    )
    return render(request, 'delivery/track.html', {'delivery': delivery})


@login_required
def available_orders(request):
    # عرض الطلبات التي حالتها 'Out' (خرجت من المطعم) ولم يستلمها دليفري بعد
    # ملاحظة: التصفية الجغرافية تحتاج GeoDjango، لكن حالياً سنعرض الأحدث
    orders = Order.objects.filter(status='Out').exclude(delivery__status='picked_up').order_by('-created_at')
    return render(request, 'delivery/available_orders.html', {'orders': orders})

@login_required
def accept_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    # إنشاء سجل توصيل جديد لهذا الدليفري
    delivery, created = Delivery.objects.get_or_create(
        order=order,
        defaults={'delivery_person': request.user, 'status': 'picked_up'}
    )
    if not created:
        delivery.delivery_person = request.user
        delivery.status = 'picked_up'
        delivery.save()
        
    return redirect('delivery:delivery_dashboard', order_id=order.id)

@login_required
def mark_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    delivery = get_object_or_404(Delivery, order=order)
    
    # تحديث الحالة في مكانين (الطلب والتوصيل)
    delivery.status = 'delivered'
    delivery.save()
    
    order.status = 'Delivered' # هاد اللي رح يظهر عند صاحب المطعم
    order.save()
    
    return redirect('delivery:available_orders')