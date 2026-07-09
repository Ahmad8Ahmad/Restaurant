"""
URL configuration for tamini project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.i18n import i18n_patterns
from django.contrib.auth import views as auth_views
from accounts import views as accounts_views
from restaurants import views as restaurants_views
from payments import views as payments_views
from tamini import views as tamini_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as media_serve
from django.contrib.staticfiles.views import serve as static_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('sw.js', tamini_views.service_worker, name='service_worker'),
    path('favicon.ico', tamini_views.favicon),
    path('payments/stripe/webhook/', payments_views.stripe_webhook, name='stripe_webhook'),
]

urlpatterns += i18n_patterns(
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('register/', accounts_views.register, name='register'),
    path('', restaurants_views.home, name='home'),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('restaurants/', include('restaurants.urls', namespace='restaurants')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('delivery/', include('delivery.urls', namespace='delivery')),
    path('payments/', include('payments.urls', namespace='payments')),
    path('support/', include('support.urls', namespace='support')),
)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [path('static/<path:path>', static_serve, {'insecure': True})]
urlpatterns += [path('media/<path:path>', media_serve, {'document_root': settings.MEDIA_ROOT})]

