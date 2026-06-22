from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem, Review
from restaurants.models import MenuItem, Restaurant
from django.contrib import messages
from django.utils.translation import gettext as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from support.models import SiteSettings
from geopy.distance import geodesic
import json

def add_to_cart(request, menu_item_id):
    item = get_object_or_404(MenuItem, id=menu_item_id)
    cart = request.session.get('cart', {})
    item_id = str(menu_item_id)

    if cart and item_id not in cart:
        existing_restaurant = None
        for cid, cdetails in cart.items():
            if 'restaurant_id' in cdetails:
                existing_restaurant = cdetails['restaurant_id']
                break
        if existing_restaurant and existing_restaurant != item.restaurant.id:
            messages.warning(request, _("السلة تحتوي على أطباق من مطعم آخر. تم إفراغ السلة لإضافة أطباق من هذا المطعم."))
            cart = {}
            request.session['cart'] = cart
            request.session['cart_count'] = 0
            request.session.modified = True

    qty = request.POST.get('quantity')
    try:
        qty = int(qty)
        if qty < 1:
            qty = 1
        elif qty > 99:
            qty = 99
    except (TypeError, ValueError):
        qty = 1

    if item_id in cart:
        new_qty = cart[item_id]['quantity'] + qty
        if new_qty > 99:
            new_qty = 99
        cart[item_id]['quantity'] = new_qty
    else:
        price = float(item.discount_price if item.discount_price else item.price)
        cart[item_id] = {
            'name': item.name,
            'price': price,
            'quantity': qty,
            'image': item.image.url if item.image else None,
            'restaurant_id': item.restaurant.id
        }

    request.session['cart'] = cart
    request.session['cart_count'] = sum(item['quantity'] for item in cart.values())
    request.session.modified = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': request.session.get('cart_count', 0),
            'cart': request.session.get('cart', {}),
            'message': str(_("تمت الإضافة"))
        })
    messages.success(request, _("تمت إضافة %(name)s إلى السلة") % {'name': item.name})
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('orders:view_cart')

def view_cart(request):
    cart = request.session.get('cart', {})
    items = []
    total = 0
    for item_id, details in cart.items():
        subtotal = details['price'] * details['quantity']
        total += subtotal
        items.append({
            'id': item_id,
            'name': details['name'],
            'price': details['price'],
            'quantity': details['quantity'],
            'subtotal': subtotal
        })
    
    # جلب طلبات المستخدم الحالية لعرضها في تبويب "تتبع طلباتك"
    orders_list = []
    if request.user.is_authenticated:
        orders_list = Order.objects.filter(customer=request.user).exclude(status='Delivered').order_by('-id')
    
    # حساب أجرة التوصيل على أساس المسافة
    customer_lat = request.session.get('customer_lat')
    customer_lng = request.session.get('customer_lng')
    delivery_fee = getattr(settings, 'DELIVERY_FEE', 5000)
    delivery_distance = None
    
    if cart and customer_lat and customer_lng:
        try:
            first_item_id = list(cart.keys())[0]
            first_item = MenuItem.objects.get(id=first_item_id)
            restaurant = first_item.restaurant
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
    cart = request.session.get('cart', {})
    item_key = str(item_id)
    action = request.POST.get('action')

    if item_key in cart:
        if action == 'increase':
            if cart[item_key]['quantity'] < 99:
                cart[item_key]['quantity'] += 1
        elif action == 'decrease':
            if cart[item_key]['quantity'] > 1:
                cart[item_key]['quantity'] -= 1
            else:
                del cart[item_key]
        request.session['cart'] = cart
        request.session['cart_count'] = sum(i['quantity'] for i in cart.values())
        request.session.modified = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': request.session.get('cart_count', 0),
            'cart': request.session.get('cart', {}),
        })
    return redirect('orders:view_cart')

def remove_from_cart(request, order_item_id):
    cart = request.session.get('cart', {})
    item_id = str(order_item_id) # نستخدم القيمة القادمة ونحولها لنص للتعامل مع السلة
    if item_id in cart:
        del cart[item_id]
        request.session['cart'] = cart
        # تحديث عداد السلة
        request.session['cart_count'] = sum(i['quantity'] for i in cart.values())
        request.session.modified = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'cart_count': request.session.get('cart_count', 0),
            'cart': request.session.get('cart', {}),
        })
    return redirect('orders:view_cart')

def checkout(request):
    if request.method == 'POST':
        cart = request.session.get('cart', {})
        if not cart:
            messages.error(request, _("سلتك فارغة"))
            return redirect('restaurants:restaurant_list')

        # Rate limiting: max 1 checkout per 10 seconds
        last_checkout = request.session.get('last_checkout_time')
        if last_checkout:
            elapsed = (timezone.now().timestamp() - last_checkout)
            if elapsed < 10:
                messages.error(request, _("يرجى الانتظار قليلاً قبل تقديم طلب جديد"))
                return redirect('orders:view_cart')

        address = request.POST.get('delivery_address', '').strip()
        delivery_lat = request.POST.get('delivery_lat')
        delivery_lng = request.POST.get('delivery_lng')
        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        current_user = request.user if request.user.is_authenticated else None
        
        if not address:
            messages.error(request, _("يرجى إدخال عنوان التوصيل"))
            return redirect('orders:view_cart')
        if not customer_phone:
            messages.error(request, _("يرجى إدخال رقم الهاتف"))
            return redirect('orders:view_cart')
        
        if not customer_name:
            customer_name = current_user.username if current_user else _("زبون")
        
        try:
            restaurant_ids = set()
            for item_id in cart.keys():
                menu_item = MenuItem.objects.get(id=item_id)
                restaurant_ids.add(menu_item.restaurant.id)
            if len(restaurant_ids) > 1:
                messages.error(request, _("لا يمكنك طلب أطباق من مطاعم مختلفة في طلب واحد. يرجى إفراغ السلة والبدء من جديد."))
                return redirect('orders:view_cart')
            first_item = MenuItem.objects.get(id=list(cart.keys())[0])
            restaurant = first_item.restaurant
        except Exception:
            return redirect('orders:view_cart')

        with transaction.atomic():
            if current_user:
                customer_order_number = Order.objects.filter(customer=current_user).count() + 1
            else:
                customer_order_number = Order.objects.filter(customer__isnull=True, customer_phone=customer_phone).count() + 1

            order = Order.objects.create(
                customer=current_user,
                customer_name=customer_name,
                customer_phone=customer_phone,
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
            
            for item_id, details in cart.items():
                menu_item = MenuItem.objects.get(id=item_id)
                subtotal = float(details['price']) * int(details['quantity'])
                total += subtotal
                
                OrderItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=details['quantity'],
                    price=details['price']
                )
                items_summary.append(f"{details['quantity']}x {menu_item.name}")

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
        request.session['last_checkout_time'] = timezone.now().timestamp()
        if delivery_lat and delivery_lng:
            request.session['customer_lat'] = float(delivery_lat)
            request.session['customer_lng'] = float(delivery_lng)
            request.session.modified = True

        # إرسال الإشعار لصاحب المطعم
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
            print(f"WebSocket Error: {e}")

        request.session['cart'] = {}
        request.session['cart_count'] = 0
        request.session.modified = True
        
        if current_user and current_user.email:
            try:
                subject = _("تأكيد الطلب -%(order_number)s - طعميني") % {'order_number': order.customer_order_number}
                html_msg = render_to_string('orders/email_confirmation.html', {
                    'order': order,
                    'items_summary': items_summary,
                    'total': grand_total,
                    'customer_name': customer_name,
                })
                send_mail(subject, '', settings.EMAIL_HOST_USER, [current_user.email],
                          fail_silently=True, html_message=html_msg)
            except Exception:
                pass

        messages.success(request, _("تم استلام طلبك بنجاح!"))
        return redirect('payments:process', order_id=order.id)
    
    return redirect('orders:view_cart')

def order_status(request):
    orders = Order.objects.none()
    if request.user.is_authenticated:
        orders = Order.objects.filter(customer=request.user).order_by('-id')
    else:
        placed_order_id = request.session.get('placed_order_id')
        if placed_order_id:
            orders = Order.objects.filter(id=placed_order_id)
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
            print(f"WebSocket Error: {e}")
        
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
            print(f"WebSocket Error: {e}")

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
            print(f"WebSocket Error: {e}")
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