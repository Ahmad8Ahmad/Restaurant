from django.shortcuts import render
from django.db.models import Q
# قم بتغيير السطرين التاليين حسب مسار الـ models عندك في المشروع
from restaurants.models import Restaurant, MenuItem 

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

    context = {
        'restaurants': restaurants,
        'menu_items': menu_items,
        'query': query,
    }
    return render(request, 'home.html', context)