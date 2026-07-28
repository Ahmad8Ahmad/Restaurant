from rest_framework import viewsets, permissions

from api.serializers import TicketSerializer, TicketCreateSerializer, TicketMessageSerializer
from support.models import Ticket, TicketMessage


class TicketViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return Ticket.objects.prefetch_related('messages').all()
        return Ticket.objects.filter(customer=user).prefetch_related('messages')

    def get_serializer_class(self):
        if self.action == 'create':
            return TicketCreateSerializer
        return TicketSerializer

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


class TicketMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TicketMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        ticket_id = self.kwargs.get('ticket_pk')
        return TicketMessage.objects.filter(ticket_id=ticket_id)

    def perform_create(self, serializer):
        ticket_id = self.kwargs.get('ticket_pk')
        serializer.save(author=self.request.user, ticket_id=ticket_id)
