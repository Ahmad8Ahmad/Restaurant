from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.view_cart, name='view_cart'),
    path('add-to-cart/<int:menu_item_id>/', views.add_to_cart, name='add_to_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('remove/<int:order_item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('update-cart/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('status/', views.order_status, name='order_status'),
    path('mark-as-out/<int:order_id>/', views.mark_as_out, name='mark_as_out'),
    path('cancel/<int:order_id>/', views.cancel_order, name='cancel_order'),
    path('customer-cancel/<int:order_id>/', views.customer_cancel_order, name='customer_cancel_order'),
    path('add_review/<int:restaurant_id>/', views.add_review, name='add_review'),
    path('delete/<int:order_id>/', views.delete_order, name='delete_order'),
]