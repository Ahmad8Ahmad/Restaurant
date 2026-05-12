import json
from channels.generic.websocket import AsyncWebsocketConsumer

# كود تتبع موقع الدليفري (اللي نقلته)
class DeliveryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['user'].id
        self.group_name = f"user_{self.user_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'delivery_location',
                'lat': data['lat'],
                'lng': data['lng']
            }
        )

    async def delivery_location(self, event):
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