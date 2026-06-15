from django.shortcuts import redirect, render, get_object_or_404
from .forms import MenuItemForm, CategoryForm, RestaurantSettingsForm
from .models import Restaurant, MenuItem, Category, HeroBanner, SiteContent
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Avg, Sum, Case, When, FloatField
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from orders.models import Review, Order
from delivery.models import Delivery
from django.contrib import messages
from django.utils.translation import gettext as _
from django.http import JsonResponse
from geopy.distance import geodesic
import json
from decimal import Decimal
from django.db.models.functions import Coalesce



def home(request):
    query = request.GET.get('q', '').strip()
    
    items = MenuItem.objects.filter(
        is_available=True,
        restaurant__is_approved=True
    ).select_related('restaurant')
    
    if query:
        items = items.filter(name__icontains=query)
    
    customer_lat = request.session.get('customer_lat')
    customer_lng = request.session.get('customer_lng')
    has_location = customer_lat and customer_lng
    
    item_distances = {}
    if has_location:
        for item in items:
            r = item.restaurant
            if r.latitude and r.longitude:
                try:
                    dist = geodesic(
                        (customer_lat, customer_lng),
                        (float(r.latitude), float(r.longitude))
                    ).km
                    item_distances[item.id] = round(dist, 1)
                except Exception:
                    pass
    
    if has_location and item_distances:
        items = sorted(items, key=lambda i: item_distances.get(i.id, float('inf')))
    else:
        items = items.order_by('-created_at')
    
    paginator = Paginator(items, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    hero_banner = HeroBanner.objects.filter(is_active=True).first()
    site_content = SiteContent.load()
    
    return render(request, 'home.html', {
        'items': page_obj,
        'page_obj': page_obj,
        'item_distances': item_distances,
        'has_location': has_location,
        'query': query,
        'hero_banner': hero_banner,
        'site_content': site_content,
    })


def restaurant_list(request):
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '').strip()
    
    restaurants = Restaurant.objects.filter(is_approved=True).annotate(
        avg_rating=Avg('reviews__rating')
    )
    
    items = MenuItem.objects.none()
    
    if query:
        restaurants = restaurants.filter(name__icontains=query)
        items = MenuItem.objects.filter(
            name__icontains=query,
            restaurant__is_approved=True
        ).select_related('restaurant')
    
    customer_lat = request.session.get('customer_lat')
    customer_lng = request.session.get('customer_lng')
    has_location = customer_lat and customer_lng
    
    if sort == 'name':
        restaurants = restaurants.order_by('name')
    elif sort == 'newest':
        restaurants = restaurants.order_by('-created_at')
    elif sort == 'nearby' and has_location:
        restaurant_list = list(restaurants)
        for r in restaurant_list:
            if r.latitude and r.longitude:
                try:
                    r._sort_dist = geodesic(
                        (customer_lat, customer_lng),
                        (float(r.latitude), float(r.longitude))
                    ).km
                except Exception:
                    r._sort_dist = float('inf')
            else:
                r._sort_dist = float('inf')
        restaurant_list.sort(key=lambda r: r._sort_dist)
        
        paginator = Paginator(restaurant_list, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        restaurant_distances = {}
        for r in page_obj:
            if r._sort_dist != float('inf'):
                restaurant_distances[r.id] = round(r._sort_dist, 1)
    else:
        restaurants = restaurants.order_by('-avg_rating')
    
    if sort != 'nearby':
        paginator = Paginator(restaurants, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        restaurant_distances = {}
        if has_location:
            for r in page_obj:
                if r.latitude and r.longitude:
                    try:
                        dist = geodesic(
                            (customer_lat, customer_lng),
                            (float(r.latitude), float(r.longitude))
                        ).km
                        restaurant_distances[r.id] = round(dist, 1)
                    except Exception:
                        pass
    
    banner = HeroBanner.objects.filter(is_active=True).first()
    site_content = SiteContent.load()
    categories = Category.objects.filter(restaurant__isnull=True)
    trendy_restaurants = Restaurant.objects.filter(is_approved=True, is_trendy=True).annotate(
        avg_rating=Avg('reviews__rating')
    )[:20]
    offer_items = MenuItem.objects.filter(
        discount_price__isnull=False,
        restaurant__is_approved=True
    ).exclude(discount_price=0).select_related('restaurant')[:20]
    return render(request, 'restaurants/restaurant_list.html', {
        'restaurants': page_obj,
        'page_obj': page_obj,
        'items': items,
        'categories': categories,
        'trendy_restaurants': trendy_restaurants,
        'offer_items': offer_items,
        'query': query,
        'current_sort': sort,
        'hero_banner': banner,
        'site_content': site_content,
        'restaurant_distances': restaurant_distances,
        'has_location': has_location,
    })

def restaurant_menu(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    menu_items = MenuItem.objects.filter(restaurant=restaurant).select_related('category')
    category_ids = menu_items.values_list('category_id', flat=True).distinct()
    categories = Category.objects.filter(id__in=category_ids)
    reviews = Review.objects.filter(restaurant=restaurant).select_related('user')
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    average_rating = round(average_rating, 1)
    reviews_count = reviews.count()
    
    paginator = Paginator(reviews, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'restaurants/restaurant_menu.html', {
        'restaurant': restaurant,
        'categories': categories,
        'menu_items': menu_items,
        'reviews': page_obj,
        'page_obj': page_obj,
        'average_rating': average_rating,
        'reviews_count': reviews_count,
    })

# <--- ضروري جداً تستورد هاي فوق

def all_menu_items(request):
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category')
    
    items = MenuItem.objects.filter(is_available=True, restaurant__is_approved=True).select_related('restaurant', 'category')
    
    if category_id:
        try:
            cat = Category.objects.get(id=category_id)
            items = items.filter(
                Q(category__name=cat.name) |
                Q(name__icontains=cat.name)
            )
        except Category.DoesNotExist:
            pass
    elif query:
        items = items.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(restaurant__name__icontains=query)
        )
    
    paginator = Paginator(items, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.filter(restaurant__isnull=True)
    banner = HeroBanner.objects.filter(is_active=True).first()
    
    return render(request, 'restaurants/all_menu_items.html', {
        'items': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'query': query,
        'hero_banner': banner,
    })



@login_required
def restaurant_dashboard(request):
    restaurant, created = Restaurant.objects.get_or_create(
        owner=request.user,
        defaults={'name': _("مطعم %(username)s") % {'username': request.user.username}, 'is_approved': False}
    )
    
    if not request.user.is_approved:
        return render(request, 'restaurants/under_review.html', {'restaurant': restaurant})
    
    # جلب الطلبات لكي تظهر في الجدول (مع استثناء الملغاة)
    orders = Order.objects.filter(restaurant=restaurant).exclude(status='Cancelled').select_related('payment').order_by('-id')
    
    items = MenuItem.objects.filter(restaurant=restaurant)
    from django.db.models import Q
    categories = Category.objects.filter(Q(menu_items__restaurant=restaurant) | Q(restaurant=restaurant)).distinct()
    
    item_form = MenuItemForm()
    item_form.fields['category'].queryset = Category.objects.filter(Q(restaurant__isnull=True) | Q(restaurant=restaurant))
    
    now = timezone.now()
    current_month = now.strftime('%B %Y')

    # استعلام منفصل للمالية — يعتمد على Delivery.status (لا يتأثر بإلغاء الطلب)
    completed_deliveries = Delivery.objects.filter(
        order__restaurant=restaurant,
        status='delivered',
        updated_at__month=now.month,
        updated_at__year=now.year
    )
    total_restaurant_orders = completed_deliveries.count()
    total_restaurant_sales = completed_deliveries.aggregate(
        total=Sum('order__total_price')
    )['total'] or 0

    context = {
        'restaurant': restaurant,
        'item_form': item_form,
        'category_form': CategoryForm(),
        'items': items,
        'categories': categories,
        'orders': orders,
        'restaurant_form': RestaurantSettingsForm(instance=restaurant),
        'total_restaurant_orders': total_restaurant_orders,
        'total_restaurant_sales': total_restaurant_sales,
        'current_month': current_month,
    }
    return render(request, 'restaurants/dashboard.html', context)


@login_required
def add_menu_item(request):
    # حماية الصفحة: فقط أصحاب المطاعم يدخلون
    if request.user.role != 'restaurant':
        return redirect('restaurants:restaurant_list')
        
    # جلب مطعم المستخدم الحالي
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.restaurant = restaurant
            item.save()
            return redirect('restaurants:restaurant_dashboard')
    else:
        form = MenuItemForm()
        form.fields['category'].queryset = Category.objects.filter(Q(restaurant__isnull=True) | Q(restaurant=restaurant))
    
    return render(request, 'restaurants/add_item.html', {'form': form})


@login_required
def add_discount(request):
    if request.user.role != 'restaurant':
        return redirect('restaurants:restaurant_list')

    restaurant = get_object_or_404(Restaurant, owner=request.user)
    
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        # تأكد أن الاسم هنا يطابق ما في الـ HTML (new_price)
        discount_price = request.POST.get('new_price')

        item = get_object_or_404(MenuItem, id=item_id, restaurant=restaurant)
        
        if discount_price:
            item.discount_price = discount_price
            item.save()
            
        return redirect('restaurants:restaurant_dashboard')

    # في حال كان الطلب GET (رغم أننا نستخدم include)
    menu_items = MenuItem.objects.filter(restaurant=restaurant)
    return render(request, 'restaurants/includes/discount_form.html', {'menu_items': menu_items})  

@login_required
def manage_menu(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    categories = Category.objects.filter(
        Q(menu_items__restaurant=restaurant) | Q(restaurant=restaurant)
    ).distinct().prefetch_related('menu_items')
    return render(request, 'restaurants/manage_menu.html', {
        'restaurant': restaurant,
        'categories': categories
    })

@login_required
def add_category(request):
    if request.method == 'POST':
        category_name = request.POST.get('name')
        category_image = request.FILES.get('image')
        if category_name:
            if request.user.is_superuser:
                Category.objects.create(name=category_name, image=category_image)
            else:
                restaurant = get_object_or_404(Restaurant, owner=request.user)
                Category.objects.create(name=category_name, image=category_image, restaurant=restaurant)
    return redirect('restaurants:restaurant_dashboard')

# تحديث بيانات المطعم (اللوغو والخلفية)
@login_required
def update_restaurant_settings(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    if request.method == 'POST':
        if request.POST.get('name'):
            restaurant.name = request.POST['name']
        if request.POST.get('description'):
            restaurant.description = request.POST['description']
        if request.POST.get('phone'):
            restaurant.phone = request.POST['phone']
        if request.POST.get('address'):
            restaurant.address = request.POST['address']
        if request.POST.get('latitude'):
            restaurant.latitude = request.POST['latitude']
        if request.POST.get('longitude'):
            restaurant.longitude = request.POST['longitude']
        if 'cover_image' in request.FILES:
            restaurant.cover_image = request.FILES['cover_image']
        restaurant.save()
        messages.success(request, _("تم تحديث البيانات بنجاح!"))
        return redirect('restaurants:restaurant_dashboard')
    form = RestaurantSettingsForm(instance=restaurant)
    return render(request, 'restaurants/includes/update_settings.html', {'form': form, 'restaurant': restaurant})

@login_required
def update_logo(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    if request.method == 'POST' and 'logo' in request.FILES:
        restaurant.logo = request.FILES['logo']
        restaurant.save()
        messages.success(request, _("تم تحديث الشعار بنجاح!"))
    return redirect('restaurants:restaurant_dashboard')


@login_required
def delete_menu_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, restaurant__owner=request.user)
    if request.method == 'POST':
        item.delete()
    return redirect('restaurants:restaurant_dashboard')

@login_required
def delete_category(request, category_id):
    if request.method != 'POST':
        return redirect('restaurants:restaurant_dashboard')
    category = get_object_or_404(Category, id=category_id)
    if request.user.is_superuser:
        if category.restaurant is not None:
            messages.error(request, _("لا يمكنك حذف تصنيف خاص بمطعم."))
            return redirect('restaurants:restaurant_dashboard')
    else:
        restaurant = get_object_or_404(Restaurant, owner=request.user)
        if category.restaurant != restaurant:
            messages.error(request, _("لا يمكنك حذف هذا التصنيف."))
            return redirect('restaurants:restaurant_dashboard')
    category.delete()
    return redirect('restaurants:restaurant_dashboard')


def restaurant_detail(request, pk):
    # 1. جلب المطعم
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    # 2. جلب المنيو (التصنيفات والأصناف التابعة لها)
    categories = Category.objects.filter(
        Q(menu_items__restaurant=restaurant) | Q(restaurant=restaurant)
    ).distinct().prefetch_related('menu_items')
    
    # 3. جلب التقييمات
    reviews = Review.objects.filter(restaurant=restaurant).select_related('user')
    
    # 4. حساب المتوسط والعدد
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    average_rating = round(average_rating, 1)
    reviews_count = reviews.count()

    # 5. إرسال كل شيء للقالب
    context = {
        'restaurant': restaurant,
        'categories': categories, # هذا السطر ضروري ليظهر الأكل
        'reviews': reviews,
        'average_rating': average_rating,
        'reviews_count': reviews_count,
    }
    
    return render(request, 'restaurants/restaurant_menu.html', context)

@csrf_exempt
@require_POST
def set_customer_location(request):
    try:
        if request.content_type and 'json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            request.session['customer_lat'] = lat
            request.session['customer_lng'] = lng
            request.session.modified = True
            return JsonResponse({'ok': True})
    except Exception:
        pass
    return JsonResponse({'ok': False}, status=400)