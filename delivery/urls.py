from django.urls import path
from . import views
app_name = 'delivery'

urlpatterns = [
    path('dashboard/<int:order_id>/', views.delivery_dashboard, name='delivery_dashboard'),
    path('track/<int:order_id>/', views.track_delivery, name='track_delivery'),
    path('available/', views.available_orders, name='available_orders'),
    path('accept/<int:order_id>/', views.accept_order, name='accept_order'),
    path('complete/<int:order_id>/', views.mark_delivered, name='complete_delivery'),
    path('set-location/', views.set_driver_location, name='set_driver_location'),
]