from unicodedata import category
from django.shortcuts import redirect, render, get_object_or_404
from .forms import MenuItemForm, CategoryForm, RestaurantSettingsForm
from .models import Restaurant, MenuItem, Category
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Avg
from orders.models import Review, Order
from django.contrib import messages



def restaurant_list(request):
    query = request.GET.get('q', '').strip()
    
    restaurants = Restaurant.objects.annotate(
        avg_rating=Avg('reviews__rating') 
    ).order_by('-avg_rating')
    
    items = MenuItem.objects.none()
    
    if query:
        restaurants = restaurants.filter(name__icontains=query)
        items = MenuItem.objects.filter(
            name__icontains=query
        )
    
    return render(request, 'restaurants/restaurant_list.html', {
        'restaurants': restaurants,
        'items': items,
        'query': query
    })

def restaurant_menu(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    categories = restaurant.categories.all()
    menu_items = MenuItem.objects.filter(category__restaurant=restaurant)
    return render(request, 'restaurants/restaurant_menu.html', {'restaurant': restaurant, 'categories': categories, 'menu_items': menu_items})

# <--- ضروري جداً تستورد هاي فوق

def all_menu_items(request):
    query = request.GET.get('q', '').strip()
    
    restaurants = Restaurant.objects.filter(is_approved=True).prefetch_related('categories')
    
    if query:
        restaurants = restaurants.filter(name__icontains=query)
    
    return render(request, 'restaurants/all_menu_items.html', {
        'restaurants': restaurants,
        'query': query
    })



@login_required
def restaurant_dashboard(request):
    restaurant, created = Restaurant.objects.get_or_create(
        owner=request.user,
        defaults={'name': f"مطعم {request.user.username}", 'is_approved': False}
    )
    
    if not restaurant.is_approved:
        return render(request, 'restaurants/under_review.html', {'restaurant': restaurant})
    
    # جلب الطلبات لكي تظهر في الجدول
    orders = Order.objects.filter(restaurant=restaurant).select_related('payment').order_by('-id')
    
    items = MenuItem.objects.filter(category__restaurant=restaurant)
    categories = Category.objects.filter(restaurant=restaurant)
    
    item_form = MenuItemForm()
    item_form.fields['category'].queryset = categories
    
    context = {
        'restaurant': restaurant,
        'item_form': item_form,
        'category_form': CategoryForm(),
        'items': items,
        'categories': categories,
        'orders': orders, # إرسال الطلبات للجدول
        'restaurant_form': RestaurantSettingsForm(instance=restaurant),
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
            # هنا نربط الوجبة بالمطعم (عبر التصنيف المختار)
            item.save()
            return redirect('restaurants:restaurant_dashboard')
    else:
        # تحديد التصنيفات الخاصة بمطعم هذا المستخدم فقط في القائمة المنسدلة
        form = MenuItemForm()
        form.fields['category'].queryset = restaurant.categories.all()
    
    return render(request, 'restaurants/add_item.html', {'form': form})


@login_required
def add_discount(request):
    if request.user.role != 'restaurant':
        return redirect('restaurants:restaurant_list')

    restaurant = get_object_or_404(Restaurant, owner=request.user)
    
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        # تأكد أن الاسم هنا يطابق ما في الـ HTML (new_price)
        discount_price = request.POST.get('discount_price') 

        # جلب الوجبة والتأكد أنها تابعة لهذا المطعم
        item = get_object_or_404(MenuItem, id=item_id, category__restaurant=restaurant)
        
        if discount_price:
            item.discount_price = discount_price # هنا نقوم بتحديث الحقل price الأساسي
            item.save() # هنا كان يحدث الخطأ
            
        return redirect('restaurants:restaurant_dashboard')

    # في حال كان الطلب GET (رغم أننا نستخدم include)
    menu_items = MenuItem.objects.filter(category__restaurant=restaurant)
    return render(request, 'restaurants/includes/discount_form.html', {'menu_items': menu_items})  

@login_required
def manage_menu(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    categories = restaurant.categories.all().prefetch_related('menu_items')
    return render(request, 'restaurants/manage_menu.html', {
        'restaurant': restaurant,
        'categories': categories
    })

@login_required
def add_category(request):
    if request.method == 'POST':
        category_name = request.POST.get('name') # الاسم القادم من input name="name"
        if category_name:
            restaurant = get_object_or_404(Restaurant, owner=request.user)
            # إنشاء التصنيف وحفظه
            Category.objects.create(
                name=category_name,
                restaurant=restaurant
            )
    return redirect('restaurants:restaurant_dashboard')

# تحديث بيانات المطعم (اللوغو والخلفية)
@login_required
def update_restaurant_settings(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    if request.method == 'POST':
        if request.POST.get('name'):
            restaurant.name = request.POST['name']
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
        messages.success(request, "تم تحديث البيانات بنجاح!")
        return redirect('restaurants:restaurant_dashboard')
    form = RestaurantSettingsForm(instance=restaurant)
    return render(request, 'restaurants/includes/update_settings.html', {'form': form, 'restaurant': restaurant})

@login_required
def update_logo(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    if request.method == 'POST' and 'logo' in request.FILES:
        restaurant.logo = request.FILES['logo']
        restaurant.save()
        messages.success(request, "تم تحديث الشعار بنجاح!")
    return redirect('restaurants:restaurant_dashboard')


@login_required
def delete_menu_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, category__restaurant__owner=request.user)
    if request.method == 'POST' or request.method == 'GET':
        item.delete()
    return redirect('restaurants:restaurant_dashboard')

@login_required
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id, restaurant__owner=request.user)
    category.delete()
    return redirect('restaurants:restaurant_dashboard')


def restaurant_detail(request, pk):
    # 1. جلب المطعم
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    # 2. جلب المنيو (التصنيفات والأصناف التابعة لها)
    # استخدمنا prefetch_related لتحسين الأداء وسرعة التحميل
    categories = Category.objects.filter(restaurant=restaurant).prefetch_related('menu_items')
    
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