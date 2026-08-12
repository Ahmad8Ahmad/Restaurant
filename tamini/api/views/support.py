from django.db.models import Prefetch

from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.serializers import (
    TicketSerializer, TicketCreateSerializer, TicketMessageSerializer,
    SiteSettingsSerializer,
)
from support.models import Ticket, TicketMessage, SiteSettings


class TicketViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Ticket.objects.prefetch_related(
        Prefetch('messages', queryset=TicketMessage.objects.select_related('author'))
    ).all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return self.queryset.filter(customer=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return TicketCreateSerializer
        return TicketSerializer

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


class TicketMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TicketMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TicketMessage.objects.select_related('author').all()

    def get_queryset(self):
        ticket_id = self.kwargs.get('ticket_pk')
        return self.queryset.filter(ticket_id=ticket_id)

    def perform_create(self, serializer):
        ticket_id = self.kwargs.get('ticket_pk')
        serializer.save(author=self.request.user, ticket_id=ticket_id)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def site_settings_view(request):
    settings = SiteSettings.get_settings()
    serializer = SiteSettingsSerializer(settings)
    return Response(serializer.data)
