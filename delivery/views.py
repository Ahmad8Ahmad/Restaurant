from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from delivery.models import Delivery
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from geopy.distance import geodesic
from orders.models import Order
import json

def _session_coords(request):
    """Get driver's last known coords from session, ignoring stale pre-fix Swedish values."""
    raw_lat = request.session.get('last_lat')
    raw_lng = request.session.get('last_lng')
    if raw_lat in (None, 55.6050, 0):
        raw_lat = 33.5138
        if 'last_lat' in request.session:
            del request.session['last_lat']
    if raw_lng in (None, 13.0038, 0):
        raw_lng = 36.2765
        if 'last_lng' in request.session:
            del request.session['last_lng']
    return raw_lat, raw_lng

@login_required
def delivery_dashboard(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        messages.error(request, "هذا الطلب لم يعد موجوداً")
        return redirect('delivery:available_orders')

    lat, lng = _session_coords(request)
    
    delivery, created = Delivery.objects.get_or_create(
        order=order,
        defaults={
            'status': 'searching',
            'current_lat': lat,
            'current_lng': lng
        }
    )
    
    if not delivery.delivery_person:
        delivery.delivery_person = request.user
        if delivery.status == 'searching':
            delivery.status = 'on_way'
    
    delivery.save()

    # نمرر الكائن باسم "delivery" وأيضاً داخل قائمة باسم "deliveries" عشان يتوافق مع القوالب عندك بدون ما تعدل شي بالـ HTML للداشبورد!
    return render(request, 'delivery/deliver_dashboard.html', {
        'delivery': delivery,
        'deliveries': [delivery],
        'order_id': order_id
    })


@login_required
def delivery_detail(request, delivery_id):
    delivery = get_object_or_404(Delivery, id=delivery_id, delivery_person=request.user)
    return render(request, 'delivery/detail.html', {'delivery': delivery})

def track_delivery(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_owner = False
    
    if request.user.is_authenticated and order.customer == request.user:
        is_owner = True
    elif request.session.get('placed_order_id') == order.id:
        is_owner = True

    if not is_owner:
        return render(request, '403.html', {'message': 'عذراً، لا يمكنك تتبع هذا الطلب.'}, status=403)

    delivery, created = Delivery.objects.get_or_create(
        order=order, 
        defaults={'current_lat': 0, 'current_lng': 0}
    )
    return render(request, 'delivery/track.html', {'delivery': delivery})

@login_required
def available_orders(request):
    curr_lat, curr_lng = _session_coords(request)

    # التعديل هنا: نجلب فقط الطلبات اللي حالتها Out والي لسه ما الها دليفري مستلمها أو مسلّمها
    orders = Order.objects.filter(status='Out').exclude(delivery__status__in=['on_way', 'picked_up', 'delivered'])

    for order in orders:
        Delivery.objects.update_or_create(
            order=order,
            defaults={
                'status': 'searching',
                'current_lat': curr_lat,
                'current_lng': curr_lng
            }
        )

    # نجلب الطلبات المتاحة للبحث فقط
    orders_with_delivery = Order.objects.filter(status='Out', delivery__status='searching').select_related('delivery', 'restaurant')
    return render(request, 'delivery/available_orders.html', {'orders': orders_with_delivery})




@login_required
def accept_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    lat, lng = _session_coords(request)

    delivery, created = Delivery.objects.get_or_create(
        order=order,
        defaults={
            'delivery_person': request.user,
            'status': 'on_way',
            'current_lat': lat,
            'current_lng': lng
        }
    )
    
    if not created:
        delivery.delivery_person = request.user
        delivery.status = 'on_way'
        delivery.current_lat = lat
        delivery.current_lng = lng
        delivery.save()

    return redirect('delivery:delivery_dashboard', order_id=order.id)

@login_required
@csrf_exempt
def set_driver_location(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        lat = data.get('lat')
        lng = data.get('lng')
        if lat is not None and lng is not None:
            request.session['last_lat'] = float(lat)
            request.session['last_lng'] = float(lng)
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def mark_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    delivery = get_object_or_404(Delivery, order=order)
    
    delivery.status = 'delivered'
    delivery.save()
    
    order.status = 'Delivered'
    order.save()
    
    return redirect('delivery:available_orders')