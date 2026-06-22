import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class DeliveryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
            return

        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.group_name = f"delivery_{self.order_id}"

        delivery, is_driver, is_customer, is_owner = await self._get_delivery_context(user)

        if not (is_driver or is_customer or is_owner or user.is_superuser):
            await self.close()
            return

        self.is_driver = is_driver

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _get_delivery_context(self, user):
        from delivery.models import Delivery
        delivery = Delivery.objects.filter(order_id=self.order_id).first()
        is_driver = delivery and delivery.delivery_person == user
        is_customer = delivery and delivery.order.customer == user
        is_owner = delivery and delivery.order.restaurant.owner == user
        return delivery, is_driver, is_customer, is_owner

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        if not getattr(self, 'is_driver', False):
            return

        data = json.loads(text_data)
        lat = data.get('lat')
        lng = data.get('lng')

        if lat is not None and lng is not None:
            if not (-90 <= float(lat) <= 90) or not (-180 <= float(lng) <= 180):
                return
            await self.save_location(lat, lng)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'delivery_location',
                'lat': lat,
                'lng': lng
            }
        )

    async def delivery_location(self, event):
        await self.send(text_data=json.dumps({
            'lat': event['lat'],
            'lng': event['lng']
        }))

    @database_sync_to_async
    def save_location(self, lat, lng):
        try:
            from delivery.models import Delivery
            delivery = Delivery.objects.filter(order_id=self.order_id).first()
            if delivery:
                delivery.current_lat = float(lat)
                delivery.current_lng = float(lng)
                delivery.save()
        except Exception as e:
            print(f"Error saving delivery location: {e}")

# كود إشعارات السائقين بالطلبات الجديدة
class DriverNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "driver_notifications"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def new_order_available(self, event):
        await self.send(text_data=json.dumps(event))

# Fallback for unmatched WebSocket paths
class FallbackConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.close()

# كود إشعارات الطلبات الجديدة
class OrderNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
            return

        self.user_id = user.id
        url_user_id = int(self.scope['url_route']['kwargs'].get('user_id', 0))
        if self.user_id != url_user_id:
            await self.close()
            return

        self.group_name = f"order_notif_{self.user_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event))