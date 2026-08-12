from django.db import transaction

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import DeliverySerializer, DriverProfileSerializer
from api.permissions import IsDeliveryPerson, IsAdmin
from delivery.models import Delivery, DriverProfile
from orders.models import Order

OUT_FOR_DELIVERY = ('Out', 'Out for Delivery')


class DeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = DeliverySerializer
    queryset = Delivery.objects.select_related('order__restaurant', 'delivery_person').all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        if user.role == 'delivery':
            return self.queryset.filter(delivery_person=user)
        return self.queryset.filter(order__customer=user)

    def get_permissions(self):
        if self.action in ('available', 'accept', 'complete', 'update_location'):
            return [permissions.IsAuthenticated(), IsDeliveryPerson()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='available')
    def available(self, request):
        if request.user.role != 'delivery':
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        # Create searchable deliveries for orders waiting to be picked up,
        # mirroring the web dashboard's lazy sync so the mobile app finds them.
        candidates = (
            Order.objects.filter(status__in=OUT_FOR_DELIVERY)
            .exclude(delivery__isnull=False)
            .select_related('restaurant')
        )
        orders = list(candidates[:100])
        existing = set(
            Delivery.objects.filter(order_id__in=[o.id for o in orders])
            .values_list('order_id', flat=True)
        )
        to_create = [
            Delivery(
                order=order,
                status='searching',
                current_lat=order.delivery_lat,
                current_lng=order.delivery_lng,
            )
            for order in orders
            if order.id not in existing
        ]
        Delivery.objects.bulk_create(to_create, ignore_conflicts=True)

        deliveries = (
            Delivery.objects.filter(status='searching', delivery_person__isnull=True)
            .select_related('order__restaurant', 'delivery_person')
            .order_by('-updated_at')
        )
        return Response(DeliverySerializer(deliveries, many=True).data)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        if request.user.role != 'delivery':
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            delivery = Delivery.objects.select_for_update().filter(pk=pk).first()
            if not delivery:
                return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
            if delivery.status != 'searching':
                return Response(
                    {'detail': 'This delivery is no longer available.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if delivery.delivery_person is not None and delivery.delivery_person != request.user:
                return Response({'detail': 'This delivery was already taken.'}, status=status.HTTP_400_BAD_REQUEST)
            delivery.delivery_person = request.user
            delivery.status = 'on_way'
            delivery.save()
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        if request.user.role != 'delivery':
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        delivery = self.get_object()
        if delivery.delivery_person != request.user:
            return Response({'detail': 'Not your delivery.'}, status=status.HTTP_403_FORBIDDEN)
        delivery.status = 'delivered'
        delivery.save()
        order = delivery.order
        if order.status in OUT_FOR_DELIVERY:
            order.status = 'Delivered'
            order.save(update_fields=['status'])
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['patch'], url_path='update-location')
    def update_location(self, request, pk=None):
        if request.user.role != 'delivery':
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
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
    queryset = DriverProfile.objects.select_related('user').all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return self.queryset.filter(user=user)
