import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem, Review, Cart, CartItem
from restaurants.models import MenuItem, Restaurant
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from support.models import SiteSettings
from geopy.distance import geodesic
from django.db.models import Sum, Prefetch
from django_ratelimit.decorators import ratelimit
import json
import requests as http_requests


def add_to_cart(request, menu_item_id):
    item = get_object_or_404(
        MenuItem.objects.select_related('restaurant'),
        id=menu_item_id,
    )
    cart = Cart.get_for_request(request)

    # Check restaurant consistency
    existing_items = cart.items.select_related('menu_item').all()
    if existing_items:
        first_restaurant = existing_items[0].menu_item.restaurant_id
        if first_restaurant != item.restaurant_id:
            cart.items.all().delete()
            messages.warning(request, _("السلة تحتوي على أطباق من مطعم آخر. تم إفراغ السلة لإضافة أطباق من هذا المطعم."))

    qty = request.POST.get('quantity')
    try:
        qty = int(qty)
        if qty < 1:
            qty = 1
        elif qty > 99:
            qty = 99
    except (TypeError, ValueError):
        qty = 1

    cart_item = cart.items.filter(menu_item=item).first()
    if cart_item:
        cart_item.quantity = min(cart_item.quantity + qty, 99)
        cart_item.save()
    else:
        CartItem.objects.create(cart=cart, menu_item=item, quantity=qty)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': cart.total_quantity(),
            'cart': cart_items_to_dict(cart),
            'message': str(_("تمت الإضافة"))
        })
    messages.success(request, _("تمت إضافة %(name)s إلى السلة") % {'name': item.name})
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('orders:view_cart')


def cart_items_to_dict(cart):
    result = {}
    for ci in cart.items.select_related('menu_item__restaurant'):
        mi = ci.menu_item
        result[str(mi.id)] = {
            'name': mi.name,
            'price': float(mi.discount_price if mi.discount_price else mi.price),
            'quantity': ci.quantity,
            'image': mi.image.url if mi.image else None,
            'restaurant_id': mi.restaurant.id,
        }
    return result

def view_cart(request):
    cart = Cart.get_for_request(request)
    cart_items_qs = cart.items.select_related('menu_item__restaurant').all()
    items = []
    total = 0
    for ci in cart_items_qs:
        subtotal = ci.subtotal()
        total += subtotal
        items.append({
            'id': ci.menu_item_id,
            'name': ci.menu_item.name,
            'price': ci.unit_price(),
            'quantity': ci.quantity,
            'subtotal': subtotal,
        })

    orders_list = []
    if request.user.is_authenticated:
        orders_list = Order.objects.filter(customer=request.user).exclude(status='Delivered').order_by('-id').select_related('restaurant')

    customer_lat = request.session.get('customer_lat')
    customer_lng = request.session.get('customer_lng')
    delivery_fee = getattr(settings, 'DELIVERY_FEE', 5000)
    delivery_distance = None

    if items and customer_lat and customer_lng:
        try:
            restaurant = cart_items_qs[0].menu_item.restaurant
            if restaurant.latitude and restaurant.longitude:
                dist = geodesic(
                    (float(customer_lat), float(customer_lng)),
                    (float(restaurant.latitude), float(restaurant.longitude))
                ).km
                site = SiteSettings.get_settings()
                base_fee = site.get('delivery_base_fee', 200)
                per_km_fee = site.get('delivery_per_km_fee', 1500)
                delivery_fee = round(base_fee + (dist * per_km_fee))
                delivery_distance = round(dist, 1)
        except Exception:
            pass

    service_fee = round(total * 0.05, 2)
    estimated_total = total + delivery_fee + service_fee
    return render(request, 'orders/cart.html', {
        'items': items,
        'total': total,
        'orders_list': orders_list,
        'delivery_fee': delivery_fee,
        'delivery_distance': delivery_distance,
        'service_fee': service_fee,
        'estimated_total': estimated_total,
    })


@require_POST
def update_cart_item(request, item_id):
    cart = Cart.get_for_request(request)
    action = request.POST.get('action')

    cart_item = cart.items.filter(menu_item_id=item_id).first()
    if cart_item:
        if action == 'increase' and cart_item.quantity < 99:
            cart_item.quantity += 1
            cart_item.save()
        elif action == 'decrease':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
            else:
                cart_item.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': cart.total_quantity(),
            'cart': cart_items_to_dict(cart),
        })
    return redirect('orders:view_cart')


def remove_from_cart(request, order_item_id):
    cart = Cart.get_for_request(request)
    cart.items.filter(menu_item_id=order_item_id).delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': 0,
            'cart': {},
        })
    return redirect('orders:view_cart')

@ratelimit(key='ip', rate='5/m', method='POST')
def checkout(request):
    if request.method == 'POST':
        cart = Cart.get_for_request(request)
        cart_items_qs = cart.items.select_related('menu_item__restaurant').all()
        if not cart_items_qs:
            messages.error(request, _("سلتك فارغة"))
            return redirect('restaurants:restaurant_list')

        address = request.POST.get('delivery_address', '').strip()
        delivery_lat = request.POST.get('delivery_lat')
        delivery_lng = request.POST.get('delivery_lng')

        if not delivery_lat or not delivery_lng:
            google_key = settings.GOOGLE_MAPS_API_KEY
            if google_key:
                try:
                    params = {'address': address, 'key': google_key}
                    resp = http_requests.get(
                        'https://maps.googleapis.com/maps/api/geocode/json',
                        params=params, timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('results'):
                            loc = data['results'][0]['geometry']['location']
                            delivery_lat = str(loc['lat'])
                            delivery_lng = str(loc['lng'])
                except Exception:
                    pass
            else:
                try:
                    params = {'q': address, 'format': 'json', 'limit': 1}
                    headers = {'User-Agent': 'Tamini/1.0'}
                    resp = http_requests.get(
                        'https://nominatim.openstreetmap.org/search',
                        params=params, headers=headers, timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data:
                            delivery_lat = data[0]['lat']
                            delivery_lng = data[0]['lon']
                except Exception:
                    pass

        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()
        current_user = request.user if request.user.is_authenticated else None
        
        if not address:
            messages.error(request, _("يرجى إدخال عنوان التوصيل"))
            return redirect('orders:view_cart')
        if not customer_phone:
            messages.error(request, _("يرجى إدخال رقم الهاتف"))
            return redirect('orders:view_cart')
        
        if not customer_name:
            customer_name = current_user.username if current_user else _("زبون")
        
        restaurant = cart_items_qs[0].menu_item.restaurant
        
        with transaction.atomic():
            if current_user:
                customer_order_number = Order.objects.filter(customer=current_user).count() + 1
            else:
                customer_order_number = Order.objects.filter(customer__isnull=True, customer_phone=customer_phone).count() + 1

            order = Order.objects.create(
                customer=current_user,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                restaurant=restaurant,
                delivery_address=address,
                delivery_lat=delivery_lat if delivery_lat else None,
                delivery_lng=delivery_lng if delivery_lng else None,
                status='Pending',
                total_price=0,
                customer_order_number=customer_order_number,
            )

            items_summary = []
            total = 0
            
            for ci in cart_items_qs:
                mi = ci.menu_item
                price = float(mi.discount_price if mi.discount_price else mi.price)
                subtotal = price * ci.quantity
                total += subtotal
                
                OrderItem.objects.create(
                    order=order,
                    menu_item=mi,
                    quantity=ci.quantity,
                    price=price,
                )
                items_summary.append(f"{ci.quantity}x {mi.name}")

            delivery_fee = getattr(settings, 'DELIVERY_FEE', 5000)
            try:
                if delivery_lat and delivery_lng and restaurant.latitude and restaurant.longitude:
                    dist = geodesic(
                        (float(delivery_lat), float(delivery_lng)),
                        (float(restaurant.latitude), float(restaurant.longitude))
                    ).km
                    site = SiteSettings.get_settings()
                    base_fee = site.get('delivery_base_fee', 200)
                    per_km_fee = site.get('delivery_per_km_fee', 1500)
                    delivery_fee = round(base_fee + (dist * per_km_fee))
            except Exception:
                pass
            service_fee = round(total * 0.05, 2)
            grand_total = total + delivery_fee + service_fee
            order.delivery_fee = delivery_fee
            order.total_price = grand_total
            order.save()

        request.session['placed_order_id'] = order.id
        if delivery_lat and delivery_lng:
            request.session['customer_lat'] = float(delivery_lat)
            request.session['customer_lng'] = float(delivery_lng)
            request.session.modified = True

        cart.items.all().delete()

        if order.customer_email:
            try:
                subject = _("تأكيد الطلب -%(order_number)s - طعميني") % {'order_number': order.customer_order_number}
                text_msg = _("مرحباً") + f" {customer_name},\n\n" + \
                           _("تم استلام طلبك رقم %(order_number)s") % {'order_number': order.customer_order_number} + "\n\n" + \
                           _("شكراً لاختيارك طعميني!")
                html_msg = render_to_string('orders/email_confirmation.html', {
                    'order': order,
                    'items_summary': items_summary,
                    'total': grand_total,
                    'customer_name': customer_name,
                })
                sent = send_mail(subject, text_msg, settings.EMAIL_HOST_USER, [order.customer_email],
                                 html_message=html_msg)
                if not sent:
                    logger.warning("Failed to send confirmation email to %s", order.customer_email)
            except Exception as e:
                logger.error("Error sending confirmation email to %s: %s", order.customer_email, e)

        # WebSocket notification after all sync operations
        try:
            channel_layer = get_channel_layer()
            group_name = f"order_notif_{restaurant.owner.id}"
            items_details_str = " | ".join(items_summary)

            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'order_id': order.id,
                    'customer_name': customer_name,
                    'items_details': items_details_str
                }
            )
        except Exception as e:
            logger.error("WebSocket Error: %s", e)

        messages.success(request, _("تم استلام طلبك بنجاح!"))
        return redirect('payments:process', order_id=order.id)
    
    return redirect('orders:view_cart')

def order_status(request):
    orders = Order.objects.none()
    if request.user.is_authenticated:
        orders = Order.objects.filter(customer=request.user).order_by('-id').select_related('restaurant', 'payment')
    else:
        placed_order_id = request.session.get('placed_order_id')
        if placed_order_id:
            orders = Order.objects.filter(id=placed_order_id).select_related('restaurant', 'payment')
    return render(request, 'orders/order_status.html', {'orders': orders})

@require_POST
def mark_as_out(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.user == order.restaurant.owner:
        order.status = 'Out'
        order.save()
        
        # إشعار السائقين بطلب متاح للتوصيل
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "driver_notifications",
                {
                    'type': 'new_order_available',
                    'message': _('طلب جديد متاح #%(order_id)s') % {'order_id': order_id},
                    'order_id': order_id
                }
            )
        except Exception as e:
            logger.error("WebSocket Error: %s", e)
        
        messages.success(request, _("الطلب رقم %(order_id)s خرج للتوصيل!") % {'order_id': order_id})
    else:
        messages.error(request, _("ليس لديك صلاحية لتعديل هذا الطلب."))
    
    return redirect('restaurants:restaurant_dashboard')

@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.user == order.restaurant.owner:
        order.status = 'Cancelled'
        order.save()
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"delivery_{order.id}",
                {
                    'type': 'delivery_location',
                    'order_deleted': True,
                    'message': _('تم إلغاء الطلب من قبل المطعم')
                }
            )
        except Exception as e:
            logger.error("WebSocket Error: %s", e)

        messages.success(request, _("تم إلغاء الطلب #%(order_id)s بنجاح") % {'order_id': order_id})
    else:
        messages.error(request, _("غير مسموح لك بإلغاء هذا الطلب"))

    return redirect('restaurants:restaurant_dashboard')




@require_POST
def customer_cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.user.is_authenticated:
        if order.customer != request.user:
            messages.error(request, _("ليس لديك صلاحية لإلغاء هذا الطلب."))
            return redirect('home')
    else:
        placed_order_id = request.session.get('placed_order_id')
        if not placed_order_id or placed_order_id != order.id:
            messages.error(request, _("ليس لديك صلاحية لإلغاء هذا الطلب."))
            return redirect('home')

    if order.status in ['Pending', 'Confirmed']:
        order.status = 'Cancelled'
        order.save()
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"order_notif_{order.restaurant.owner.id}",
                {
                    'type': 'send_notification',
                    'message': _('تم إلغاء الطلب #%(order_id)s من قبل العميل.') % {'order_id': order.id},
                    'order_id': order.id,
                }
            )
        except Exception as e:
            logger.error("WebSocket Error: %s", e)
        messages.success(request, _("تم إلغاء الطلب #%(order_id)s بنجاح.") % {'order_id': order_id})
    else:
        messages.error(request, _("لا يمكن إلغاء الطلب بعد بدء التحضير."))
    return redirect('home')


@require_POST
def delete_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.user.is_authenticated:
        if order.customer != request.user:
            messages.error(request, _("ليس لديك صلاحية لحذف هذا الطلب."))
            return redirect('orders:order_status')
    else:
        placed_order_id = request.session.get('placed_order_id')
        if not placed_order_id or placed_order_id != order.id:
            messages.error(request, _("ليس لديك صلاحية لحذف هذا الطلب."))
            return redirect('orders:order_status')

    if order.status in ['Completed', 'Delivered', 'Cancelled']:
        order.delete()
        messages.success(request, _("تم حذف الطلب بنجاح."))
    else:
        messages.error(request, _("لا يمكن حذف الطلب قبل اكتماله."))
    return redirect('orders:order_status')


@login_required
def add_review(request, restaurant_id):
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        restaurant = get_object_or_404(Restaurant, id=restaurant_id)
        
        # إنشاء التقييم وحفظه
        Review.objects.create(
            user=request.user,
            restaurant=restaurant,
            rating=rating,
            comment=comment
        )
        
        messages.success(request, _("شكراً لك! تم إضافة تقييمك بنجاح."))
        # العودة لصفحة المنيو الخاصة بنفس المطعم
        return redirect('restaurants:restaurant_menu', restaurant_id=restaurant_id)
    
    return redirect('restaurants:restaurant_list')