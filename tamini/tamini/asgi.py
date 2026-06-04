import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tamini.settings')
# لازم نخلي التطبيق الأساسي يشتغل أولاً
django_asgi_app = get_asgi_application()

# الاستيراد لازم يكون هنا بعد الـ django_asgi_app
from orders.routing import websocket_urlpatterns as order_ws
from support.routing import websocket_urlpatterns as support_ws

websocket_urlpatterns = order_ws + support_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})