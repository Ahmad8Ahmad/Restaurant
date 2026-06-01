from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from delivery.models import Delivery
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from django.utils import timezone
from django.contrib import messages
from geopy.distance import geodesic
from orders.models import Order
import urllib.parse
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
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')

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
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
    delivery = get_object_or_404(Delivery, id=delivery_id, delivery_person=request.user)
    return render(request, 'delivery/detail.html', {'delivery': delivery})

def track_delivery(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return render(request, 'delivery/track.html', {
            'order_exists': False,
            'error_message': 'عذراً، هذا الطلب غير موجود أو تم إلغاؤه',
        })

    is_owner = False
    
    if request.user.is_authenticated and order.customer == request.user:
        is_owner = True
    elif request.session.get('placed_order_id') == order.id:
        is_owner = True

    if not is_owner:
        return render(request, 'delivery/track.html', {
            'order_exists': False,
            'error_message': 'عذراً، لا يمكنك تتبع هذا الطلب.',
        })

    delivery, created = Delivery.objects.get_or_create(
        order=order, 
        defaults={'current_lat': 0, 'current_lng': 0}
    )
    return render(request, 'delivery/track.html', {'delivery': delivery, 'order_exists': True})

def _driver_approved(user):
    return user.is_approved

@login_required
def available_orders(request):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
    curr_lat, curr_lng = _session_coords(request)

    now = timezone.now()
    completed_this_month = Delivery.objects.filter(
        delivery_person=request.user,
        status='delivered',
        updated_at__month=now.month,
        updated_at__year=now.year
    )

    total_orders = completed_this_month.count()
    total_km = sum(d.calculate_distance() for d in completed_this_month)
    total_delivery_earnings = sum(d.delivery_fee for d in completed_this_month)
    total_food_cash = completed_this_month.filter(is_settled=False).aggregate(
        total=Sum('order__total_price')
    )['total'] or 0

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
    return render(request, 'delivery/available_orders.html', {
        'orders': orders_with_delivery,
        'total_orders': total_orders,
        'total_km': total_km,
        'total_delivery_earnings': total_delivery_earnings,
        'total_food_cash': total_food_cash,
    })




@login_required
def accept_order(request, order_id):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
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
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
    order = get_object_or_404(Order, id=order_id)
    delivery = get_object_or_404(Delivery, order=order)

    lat, lng = _session_coords(request)
    delivery.current_lat = lat
    delivery.current_lng = lng
    delivery.status = 'delivered'
    delivery.save()

    order.status = 'Delivered'
    order.save()

    return redirect('delivery:available_orders')

@login_required
def pending_approval(request):
    return render(request, 'delivery/pending_approval.html')

@login_required
def driver_finance_dashboard(request):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')

    driver = request.user
    now = timezone.now()
    completed_deliveries = Delivery.objects.filter(
        delivery_person=driver,
        status='delivered',
        updated_at__month=now.month,
        updated_at__year=now.year
    )

    total_trips = completed_deliveries.count()
    total_delivery_fees = sum(d.delivery_fee for d in completed_deliveries)
    total_cash_collected = completed_deliveries.filter(is_settled=False).aggregate(
        total=Sum('order__total_price')
    )['total'] or 0

    whatsapp_msg = (
        f"مرحباً، أنا السائق {driver.username}. "
        f"أود مراجعة حساباتي لشهر {now.month}. "
        f"عدد المشاوير: {total_trips} | "
        f"أجور التوصيل: {total_delivery_fees} ل.س."
    )
    encoded_msg = urllib.parse.quote(whatsapp_msg)
    whatsapp_url = f"https://wa.me/963900000000?text={encoded_msg}"

    return render(request, 'delivery/finance_dashboard.html', {
        'total_trips': total_trips,
        'total_delivery_fees': total_delivery_fees,
        'total_cash_collected': total_cash_collected,
        'whatsapp_url': whatsapp_url,
        'deliveries': completed_deliveries,
        'month': now.month,
        'year': now.year,
    })