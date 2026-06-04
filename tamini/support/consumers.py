import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Ticket, TicketMessage


class LiveChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.room = None

        if self.user.is_authenticated and (self.user.is_staff or self.user.is_superuser):
            self.room = f"chat_staff_{self.user.id}"
            await self.channel_layer.group_add(self.room, self.channel_name)
            await self.accept()
            await self.send_active_chats()
            return

        if self.user.is_authenticated:
            self.room = f"chat_user_{self.user.id}"
            await self.channel_layer.group_add(self.room, self.channel_name)
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'chat_history',
                'messages': await self.get_user_chat_history(),
            }))
            await self.channel_layer.group_send(
                'chat_staff',
                {
                    'type': 'user_connected',
                    'user_id': self.user.id,
                    'username': self.user.username,
                }
            )
            return

        await self.close()

    async def disconnect(self, close_code):
        if self.room:
            await self.channel_layer.group_discard(self.room, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type', 'message')
        message = data.get('message', '').strip()

        if not message:
            return

        if self.user.is_staff or self.user.is_superuser:
            user_id = data.get('user_id')
            msg = await self.save_staff_message(user_id, message)
            if msg:
                await self.channel_layer.group_send(
                    f"chat_user_{user_id}",
                    {
                        'type': 'chat_message',
                        'message': message,
                        'author': 'الدعم',
                        'timestamp': str(msg.created_at),
                    }
                )
        else:
            msg = await self.save_user_message(message)
            if msg:
                await self.channel_layer.group_send(
                    'chat_staff',
                    {
                        'type': 'chat_message',
                        'message': message,
                        'author': self.user.username,
                        'user_id': self.user.id,
                        'timestamp': str(msg.created_at),
                    }
                )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_connected(self, event):
        await self.send(text_data=json.dumps(event))

    async def send_active_chats(self):
        chats = await self.get_active_chats()
        await self.send(text_data=json.dumps({
            'type': 'active_chats',
            'chats': chats,
        }))

    @database_sync_to_async
    def get_active_chats(self):
        from accounts.models import User
        from django.db.models import Max
        active_ids = (
            Ticket.objects.filter(status__in=['open', 'in_progress'])
            .values('customer')
            .distinct()
        )
        users = User.objects.filter(id__in=[a['customer'] for a in active_ids if a['customer']])
        return [{'id': u.id, 'username': u.username} for u in users]

    @database_sync_to_async
    def get_user_chat_history(self):
        ticket = Ticket.objects.filter(customer=self.user).last()
        if not ticket:
            return []
        msgs = ticket.messages.all()[:50]
        return [{
            'message': m.message,
            'author': m.author_name,
            'timestamp': str(m.created_at),
        } for m in msgs]

    @database_sync_to_async
    def save_user_message(self, message):
        ticket = Ticket.objects.filter(customer=self.user, status__in=['open', 'in_progress']).last()
        if not ticket:
            ticket = Ticket.objects.create(
                customer=self.user,
                customer_name=self.user.username,
                customer_email=self.user.email,
                subject='محادثة مباشرة',
                description=message,
                priority='medium',
            )
        return TicketMessage.objects.create(
            ticket=ticket,
            author=self.user,
            author_name=self.user.username,
            message=message,
        )

    @database_sync_to_async
    def save_staff_message(self, user_id, message):
        ticket = Ticket.objects.filter(customer_id=user_id, status__in=['open', 'in_progress']).last()
        if not ticket:
            ticket = Ticket.objects.filter(customer_id=user_id).last()
            if ticket:
                ticket.status = 'in_progress'
                ticket.save()
        if not ticket:
            return None
        return TicketMessage.objects.create(
            ticket=ticket,
            author=self.user,
            author_name=f'الدعم - {self.user.username}',
            message=message,
        )
