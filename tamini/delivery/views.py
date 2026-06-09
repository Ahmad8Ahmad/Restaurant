from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from delivery.models import Delivery
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone
from django.contrib import messages
from django.utils.translation import gettext as _
from orders.models import Order
import urllib.parse
import json
import logging

logger = logging.getLogger(__name__)

def _session_coords(request):
    raw_lat = request.session.get('last_lat')
    raw_lng = request.session.get('last_lng')
    if not raw_lat or not raw_lng:
        return 33.5138, 36.2765
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return 33.5138, 36.2765
        return lat, lng
    except (TypeError, ValueError):
        return 33.5138, 36.2765

@login_required
def delivery_dashboard(request, order_id):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        messages.error(request, _("هذا الطلب لم يعد موجوداً"))
        return redirect('delivery:available_orders')

    lat, lng = _session_coords(request)
    
    with transaction.atomic():
        delivery = Delivery.objects.select_for_update().filter(order=order).first()
        if not delivery:
            restaurant = order.restaurant
            try:
                lat = float(restaurant.latitude) if restaurant.latitude else 33.5138
                lng = float(restaurant.longitude) if restaurant.longitude else 36.2765
            except (TypeError, ValueError):
                lat, lng = 33.5138, 36.2765
            delivery = Delivery.objects.create(
                order=order,
                status='searching',
                current_lat=lat,
                current_lng=lng
            )
        
        if not delivery.delivery_person:
            delivery.delivery_person = request.user
            if delivery.status == 'searching':
                delivery.status = 'on_way'
                delivery.save()
        elif delivery.delivery_person != request.user:
            messages.error(request, "هذا الطلب تم استلامه من قبل سائق آخر.")
            return redirect('delivery:available_orders')

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
            'error_message': _('عذراً، هذا الطلب غير موجود أو تم إلغاؤه'),
        })

    is_owner = False
    
    if request.user.is_authenticated and order.customer == request.user:
        is_owner = True
    elif request.session.get('placed_order_id') == order.id:
        is_owner = True

    if not is_owner:
        return render(request, 'delivery/track.html', {
            'order_exists': False,
            'error_message': _('عذراً، لا يمكنك تتبع هذا الطلب.'),
        })

    delivery = Delivery.objects.filter(order=order).first()
    if not delivery:
        return render(request, 'delivery/track.html', {
            'order_exists': False,
            'error_message': _('لم يتم تعيين سائق بعد. سيتم التحديث عند تعيين سائق.'),
        })
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
    total_km = sum(d.cached_distance for d in completed_this_month)
    total_delivery_earnings = sum(d.cached_fee for d in completed_this_month)
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
    
    paginator = Paginator(orders_with_delivery, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'delivery/available_orders.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'total_orders': total_orders,
        'total_km': total_km,
        'total_delivery_earnings': total_delivery_earnings,
        'total_food_cash': total_food_cash,
    })




@require_POST
@login_required
def accept_order(request, order_id):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
    order = get_object_or_404(Order, id=order_id)
    lat, lng = _session_coords(request)

    with transaction.atomic():
        delivery = Delivery.objects.select_for_update().filter(order=order).first()
        if delivery:
            if delivery.delivery_person and delivery.delivery_person != request.user and delivery.status != 'delivered':
                messages.error(request, _("هذا الطلب تم استلامه من قبل سائق آخر."))
                return redirect('delivery:available_orders')
            if delivery.delivery_person == request.user and delivery.status == 'delivered':
                messages.error(request, _("هذا الطلب مكتمل بالفعل."))
                return redirect('delivery:available_orders')
        
        if not delivery:
            delivery = Delivery.objects.create(
                order=order,
                delivery_person=request.user,
                status='on_way',
                current_lat=lat,
                current_lng=lng
            )
        else:
            delivery.delivery_person = request.user
            delivery.status = 'on_way'
            delivery.current_lat = lat
            delivery.current_lng = lng
            delivery.save()

    return redirect('delivery:delivery_dashboard', order_id=order.id)

@login_required
def set_driver_location(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = float(data.get('lat', 0))
            lng = float(data.get('lng', 0))
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return JsonResponse({'status': 'error', 'message': _('إحداثيات غير صالحة')}, status=400)
            request.session['last_lat'] = lat
            request.session['last_lng'] = lng
            return JsonResponse({'status': 'ok'})
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid location data from driver {request.user.id}: {e}")
            return JsonResponse({'status': 'error', 'message': _('بيانات غير صالحة')}, status=400)
    return JsonResponse({'status': 'error'}, status=400)

@require_POST
@login_required
def mark_delivered(request, order_id):
    if not _driver_approved(request.user):
        return redirect('delivery:pending_approval')
    order = get_object_or_404(Order, id=order_id)
    delivery = get_object_or_404(Delivery, order=order, delivery_person=request.user)

    lat, lng = _session_coords(request)
    delivery.current_lat = lat
    delivery.current_lng = lng
    delivery.status = 'delivered'
    delivery.save(update_fields=['current_lat', 'current_lng', 'status', 'updated_at'])

    order.status = 'Delivered'
    order.save(update_fields=['status'])

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
    total_delivery_fees = sum(d.cached_fee for d in completed_deliveries)
    total_cash_collected = completed_deliveries.filter(is_settled=False).aggregate(
        total=Sum('order__total_price')
    )['total'] or 0

    whatsapp_msg = _(
        "مرحباً، أنا السائق %(username)s. "
        "أود مراجعة حساباتي لشهر %(month)s. "
        "عدد المشاوير: %(trips)s | "
        "أجور التوصيل: %(fees)s ل.س."
    ) % {'username': driver.username, 'month': now.month, 'trips': total_trips, 'fees': total_delivery_fees}
    encoded_msg = urllib.parse.quote(whatsapp_msg)
    whatsapp_number = getattr(settings, 'WHATSAPP_SUPPORT_NUMBER', '963900000000')
    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_msg}"

    return render(request, 'delivery/finance_dashboard.html', {
        'total_trips': total_trips,
        'total_delivery_fees': total_delivery_fees,
        'total_cash_collected': total_cash_collected,
        'whatsapp_url': whatsapp_url,
        'deliveries': completed_deliveries,
        'month': now.month,
        'year': now.year,
    })