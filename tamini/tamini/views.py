from django.shortcuts import render, redirect
from django.db.models import Q
from django.http import HttpResponse
from django.template import loader
# قم بتغيير السطرين التاليين حسب مسار الـ models عندك في المشروع
from restaurants.models import Restaurant, MenuItem, Category


def service_worker(request):
    template = loader.get_template('sw.js')
    response = HttpResponse(template.render(), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response

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