from django.shortcuts import render, redirect
from django.db.models import Q
# قم بتغيير السطرين التاليين حسب مسار الـ models عندك في المشروع
from restaurants.models import Restaurant, MenuItem, Category

def home(request):
    query = request.GET.get('q', '').strip()
    
    # جلب كل المطاعم والوجبات بشكل افتراضي
    restaurants = Restaurant.objects.all()
    menu_items = MenuItem.objects.all()
    
    # إذا كان هناك كلمة بحث، يتم الفلترة فوراً
    if query:
        restaurants = restaurants.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        menu_items = menu_items.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    categories = Category.objects.all()

    context = {
        'restaurants': restaurants,
        'menu_items': menu_items,
        'categories': categories,
        'query': query,
    }
    return render(request, 'home.html', context)


def csrf_failure(request, reason=""):
    return redirect('home')