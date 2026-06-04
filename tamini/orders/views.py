from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from .models import Order, OrderItem, Review
from restaurants.models import MenuItem, Restaurant
from django.contrib import messages
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import json

def add_to_cart(request, menu_item_id):
    item = get_object_or_404(MenuItem, id=menu_item_id)
    cart = request.session.get('cart', {})
    item_id = str(menu_item_id)

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
        # نجلب الطلبات التي لم تكتمل بعد (Pending و Out) لتظهر في التتبع
        orders_list = Order.objects.filter(customer=request.user).exclude(status='Delivered').order_by('-id')
    
    delivery_fee = getattr(settings, 'DELIVERY_FEE', 5000)
    service_fee = round(total * 0.05, 2)
    estimated_total = total + delivery_fee + service_fee
    return render(request, 'orders/cart.html', {
        'items': items,
        'total': total,
        'orders_list': orders_list,
        'delivery_fee': delivery_fee,
        'service_fee': service_fee,
        'estimated_total': estimated_total,
    })
 



def remove_from_cart(request, order_item_id):
    cart = request.session.get('cart', {})
    item_id = str(order_item_id) # نستخدم القيمة القادمة ونحولها لنص للتعامل مع السلة
    if item_id in cart:
        del cart[item_id]
        request.session['cart'] = cart
        # تحديث عداد السلة
        request.session['cart_count'] = sum(i['quantity'] for i in cart.values())
        request.session.modified = True
    return redirect('orders:view_cart')

def checkout(request):
    if request.method == 'POST':
        cart = request.session.get('cart', {})
        if not cart:
            messages.error(request, "سلتك فارغة")
            return redirect('restaurants:restaurant_list')

        address = request.POST.get('delivery_address')
        delivery_lat = request.POST.get('delivery_lat')
        delivery_lng = request.POST.get('delivery_lng')
        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        current_user = request.user if request.user.is_authenticated else None
        
        if not customer_name:
            customer_name = current_user.username if current_user else "زبون"
        
        try:
            first_item_id = list(cart.keys())[0]
            first_item = MenuItem.objects.get(id=first_item_id)
            restaurant = first_item.restaurant
        except Exception as e:
            return redirect('orders:view_cart')

        order = Order.objects.create(
            customer=current_user,
            customer_name=customer_name,
            customer_phone=customer_phone,
            restaurant=restaurant,
            delivery_address=address,
            delivery_lat=delivery_lat if delivery_lat else None,
            delivery_lng=delivery_lng if delivery_lng else None,
            status='Pending',
            total_price=0
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
        service_fee = round(total * 0.05, 2)
        grand_total = total + delivery_fee + service_fee
        order.total_price = grand_total
        order.save()
        request.session['placed_order_id'] = order.id

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
        
        messages.success(request, "تم استلام طلبك بنجاح!")
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
                    'message': f'طلب جديد متاح #{order_id}',
                    'order_id': order_id
                }
            )
        except Exception as e:
            print(f"WebSocket Error: {e}")
        
        messages.success(request, f"الطلب رقم {order_id} خرج للتوصيل!")
    else:
        messages.error(request, "ليس لديك صلاحية لتعديل هذا الطلب.")
    
    return redirect('restaurants:restaurant_dashboard')

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
                    'message': 'تم إلغاء الطلب من قبل المطعم'
                }
            )
        except Exception as e:
            print(f"WebSocket Error: {e}")

        messages.success(request, f"تم إلغاء الطلب #{order_id} بنجاح")
    else:
        messages.error(request, "غير مسموح لك بإلغاء هذا الطلب")

    return redirect('restaurants:restaurant_dashboard')




def customer_cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.user.is_authenticated:
        if order.customer != request.user:
            messages.error(request, "ليس لديك صلاحية لإلغاء هذا الطلب.")
            return redirect('home')
    else:
        placed_order_id = request.session.get('placed_order_id')
        if not placed_order_id or placed_order_id != order.id:
            messages.error(request, "ليس لديك صلاحية لإلغاء هذا الطلب.")
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
                    'message': f'تم إلغاء الطلب #{order.id} من قبل العميل.',
                    'order_id': order.id,
                }
            )
        except Exception as e:
            print(f"WebSocket Error: {e}")
        messages.success(request, f"تم إلغاء الطلب #{order_id} بنجاح.")
    else:
        messages.error(request, "لا يمكن إلغاء الطلب بعد بدء التحضير.")
    return redirect('home')


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
        
        messages.success(request, "شكراً لك! تم إضافة تقييمك بنجاح.")
        # العودة لصفحة المنيو الخاصة بنفس المطعم
        return redirect('restaurants:restaurant_menu', restaurant_id=restaurant_id)
    
    return redirect('restaurants:restaurant_list')