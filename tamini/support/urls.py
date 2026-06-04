from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('create/', views.create_ticket, name='create_ticket'),
    path('my-tickets/', views.my_tickets, name='my_tickets'),
    path('ticket/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('admin-tickets/', views.manage_tickets, name='manage_tickets'),
    path('admin-tickets/<int:ticket_id>/', views.manage_ticket_detail, name='manage_ticket_detail'),
]
