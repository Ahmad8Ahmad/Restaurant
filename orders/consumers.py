import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class DeliveryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.group_name = f"delivery_{self.order_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        lat = data.get('lat')
        lng = data.get('lng')

        if lat is not None and lng is not None:
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

# كود إشعارات الطلبات الجديدة
class OrderNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # بنجيب الـ ID تبع صاحب المطعم اللي مسجل دخول حالياً
        self.user_id = self.scope['user'].id
        self.group_name = f"order_notif_{self.user_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event))