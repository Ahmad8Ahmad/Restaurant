from django.urls import re_path
# استيراد مباشر وصريح
from orders import consumers 

websocket_urlpatterns = [
    re_path(r'ws/delivery/(?P<order_id>\d+)/$', consumers.DeliveryConsumer.as_asgi()),
    re_path(r'ws/notifications/(?P<user_id>\d+)/$', consumers.OrderNotificationConsumer.as_asgi()),
    re_path(r'ws/driver-notifications/$', consumers.DriverNotificationConsumer.as_asgi()),
]