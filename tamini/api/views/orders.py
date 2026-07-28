import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    OrderSerializer, OrderCreateSerializer, OrderItemSerializer, ReviewSerializer
)
from api.permissions import IsCustomer
from orders.models import Order, OrderItem, Review, Cart
from restaurants.models import MenuItem
from support.models import SiteSettings

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return Order.objects.select_related('restaurant', 'customer').prefetch_related('items').all()
        if user.role == 'restaurant':
            return Order.objects.filter(restaurant__owner=user).select_related('restaurant', 'customer').prefetch_related('items')
        return Order.objects.filter(customer=user).select_related('restaurant', 'customer').prefetch_related('items')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def checkout(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        restaurant = data['restaurant_id']

        with transaction.atomic():
            settings_data = SiteSettings.get_settings()
            delivery_fee = settings_data.get('delivery_base_fee', 5000)

            total = 0
            order_items_data = []
            for item_data in data['items']:
                try:
                    mi = MenuItem.objects.get(id=item_data['menu_item_id'], restaurant=restaurant, is_available=True)
                except MenuItem.DoesNotExist:
                    return Response(
                        {'detail': f"Menu item {item_data['menu_item_id']} not found or unavailable."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                price = mi.discount_price if mi.discount_price else mi.price
                qty = item_data['quantity']
                total += float(price) * qty
                order_items_data.append({'menu_item': mi, 'quantity': qty, 'price': price})

            order = Order.objects.create(
                customer=request.user,
                customer_name=data.get('customer_name', ''),
                customer_phone=data.get('customer_phone', ''),
                customer_email=data.get('customer_email', request.user.email),
                restaurant=restaurant,
                delivery_address=data['delivery_address'],
                delivery_lat=data.get('delivery_lat'),
                delivery_lng=data.get('delivery_lng'),
                delivery_fee=delivery_fee,
                total_price=total + delivery_fee,
                status='Pending',
            )

            for oi in order_items_data:
                OrderItem.objects.create(order=order, **oi)

            Cart.objects.filter(user=request.user).delete()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        valid = [s for s, _ in Order.STATUS_CHOICES]
        if new_status not in valid:
            return Response({'detail': f'Invalid status. Choose from: {valid}'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = new_status
        order.save()
        return Response(OrderSerializer(order).data)


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Review.objects.select_related('user', 'restaurant')
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrderTicketViewSet(viewsets.ReadOnlyModelViewSet):
    from api.serializers import OrderTicketSerializer
    serializer_class = OrderTicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from orders.models import Ticket as OT
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return OT.objects.all()
        return OT.objects.filter(customer=user)
