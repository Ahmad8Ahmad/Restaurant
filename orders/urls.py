from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.view_cart, name='view_cart'),
    path('add-to-cart/<int:menu_item_id>/', views.add_to_cart, name='add_to_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('remove/<int:order_item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('status/', views.order_status, name='order_status'),
    path('mark-as-out/<int:order_id>/', views.mark_as_out, name='mark_as_out'),
    path('delete/<int:order_id>/', views.delete_order, name='delete_order'),
]