from django.urls import path
from . import views

app_name = 'user_settings'

urlpatterns = [
    path('', views.settings_view, name='settings'),
    path('toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    path('toggle-notification/<str:key>/', views.toggle_notification, name='toggle_notification'),
]
