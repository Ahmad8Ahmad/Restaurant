from django.shortcuts import render, redirect, get_object_or_404
from .models import Order, OrderItem
from restaurants.models import MenuItem
from django.contrib import messages
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import json

def add_to_cart(request, menu_item_id):
    item = get_object_or_404(MenuItem, id=menu_item_id)
    cart = request.session.get('cart', {})
    item_id = str(menu_item_id)

    if item_id in cart:
        cart[item_id]['quantity'] += 1
    else:
        price = float(item.discount_price if item.discount_price else item.price)
        cart[item_id] = {
            'name': item.name,
            'price': price,
            'quantity': 1,
            'image': item.image.url if item.image else None,
            'restaurant_id': item.category.restaurant.id # احتفظنا بمعرف المطعم
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
    return render(request, 'orders/cart.html', {'items': items, 'total': total})

def remove_from_cart(request, item_id):
    cart = request.session.get('cart', {})
    item_id = str(item_id)
    if item_id in cart:
        del cart[item_id]
        request.session['cart'] = cart
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
        current_user = request.user if request.user.is_authenticated else None
        
        try:
            first_item_id = list(cart.keys())[0]
            first_item = MenuItem.objects.get(id=first_item_id)
            restaurant = first_item.category.restaurant
        except Exception as e:
            return redirect('orders:view_cart')

        # إنشاء الطلب
        order = Order.objects.create(
            customer=current_user,
            restaurant=restaurant,
            delivery_address=address,
            status='Pending',
            total_price=0
        )

        total = 0
        items_summary = []
        
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

        order.total_price = total
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
                    'customer_name': current_user.username if current_user else "زبون زائر",
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
    if request.user.is_authenticated:
        orders = Order.objects.filter(customer=request.user).order_by('-id')
    else:
        # للزوار، قد لا تظهر الطلبات القديمة إلا إذا استخدمت نظاماً آخر، حالياً نتركها فارغة
        orders = []
    return render(request, 'orders/order_status.html', {'orders': orders})

def mark_as_out(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # التأكد أن صاحب المطعم هو من يغير الحالة
    if request.user == order.restaurant.owner:
        # نصيحة: استخدم 'Out' بدلاً من 'Out for Delivery' لتسهيل الشرط في HTML
        order.status = 'Out for Delivery' 
        order.save()
        messages.success(request, f"الطلب رقم {order_id} خرج للتوصيل!")
    else:
        messages.error(request, "ليس لديك صلاحية لتعديل هذا الطلب.")
    
    # التأكد من كتابة اسم المسار كاملاً
    return redirect('restaurants:restaurant_dashboard')

def delete_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    # التأكد أن صاحب المطعم هو من يحذف الطلب
    if request.user == order.restaurant.owner:
        order.delete()
        messages.success(request, f"تم حذف الطلب #{order_id} بنجاح")
    else:
        messages.error(request, "غير مسموح لك بحذف هذا الطلب")
        
    return redirect('restaurants:restaurant_dashboard')
