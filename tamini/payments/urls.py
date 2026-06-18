from django.urls import path
from . import views
app_name = 'payments'
urlpatterns = [
    path('process/<int:order_id>/', views.process_payment, name='process'),
    path('stripe/success/<int:order_id>/', views.stripe_success, name='stripe_success'),
    path('stripe/cancel/<int:order_id>/', views.stripe_cancel, name='stripe_cancel'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
]
