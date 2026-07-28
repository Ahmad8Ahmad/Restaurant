from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import DeliverySerializer, DriverProfileSerializer
from api.permissions import IsDeliveryPerson, IsAdmin
from delivery.models import Delivery, DriverProfile


class DeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = DeliverySerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return Delivery.objects.select_related('order__restaurant', 'delivery_person').all()
        if user.role == 'delivery':
            return Delivery.objects.filter(delivery_person=user).select_related('order__restaurant', 'delivery_person')
        return Delivery.objects.filter(order__customer=user).select_related('order__restaurant', 'delivery_person')

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='available')
    def available(self, request):
        if request.user.role != 'delivery':
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        deliveries = Delivery.objects.filter(
            status='searching', delivery_person__isnull=True
        ).select_related('order__restaurant')
        return Response(DeliverySerializer(deliveries, many=True).data)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        delivery = self.get_object()
        if delivery.status != 'searching':
            return Response({'detail': 'This delivery is no longer available.'}, status=status.HTTP_400_BAD_REQUEST)
        delivery.delivery_person = request.user
        delivery.status = 'on_way'
        delivery.save()
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        delivery = self.get_object()
        if delivery.delivery_person != request.user:
            return Response({'detail': 'Not your delivery.'}, status=status.HTTP_403_FORBIDDEN)
        delivery.status = 'delivered'
        delivery.save()
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['patch'], url_path='update-location')
    def update_location(self, request, pk=None):
        delivery = self.get_object()
        lat = request.data.get('current_lat')
        lng = request.data.get('current_lng')
        if lat is None or lng is None:
            return Response({'detail': 'current_lat and current_lng are required.'}, status=status.HTTP_400_BAD_REQUEST)
        delivery.current_lat = lat
        delivery.current_lng = lng
        delivery.save()
        return Response(DeliverySerializer(delivery).data)


class DriverProfileViewSet(viewsets.ModelViewSet):
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return DriverProfile.objects.select_related('user').all()
        return DriverProfile.objects.filter(user=user).select_related('user')
