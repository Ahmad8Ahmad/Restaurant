from django.urls import path
from . import views
app_name = 'payments'
urlpatterns = [
    path('process/<int:order_id>/', views.process_payment, name='process'),
    path('success/<int:order_id>/', views.process_payment, name='success'),
   
]