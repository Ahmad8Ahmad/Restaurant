import logging

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    OrderSerializer, OrderCreateSerializer, OrderItemSerializer,
    OrderTrackingSerializer, ReviewSerializer,
)
from api.permissions import IsCustomer
from orders.models import Order, OrderItem, Review, Cart
from orders.pricing import quote as pricing_quote
from payments.providers import get_provider
from payments.providers.base import PaymentError
from payments.services import initiate_payment
from restaurants.models import MenuItem

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.select_related(
        'restaurant', 'customer', 'delivery__delivery_person',
    ).prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related('menu_item'))
    ).order_by('-created_at')

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            qs = self.queryset
        elif user.role == 'restaurant':
            qs = self.queryset.filter(restaurant__owner=user)
        elif user.role == 'staff':
            qs = self.queryset.filter(restaurant_id=user.restaurant_id)
        else:
            qs = self.queryset.filter(customer=user)
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        return qs

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

        if not restaurant.is_active:
            return Response(
                {'detail': _('هذا المطعم مغلق حالياً')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve the requested payment method up front. If the gateway is
        # disabled we fail here, before any row is written, so a declined
        # payment method can't leave an orphaned Pending order behind.
        payment_method = data.get('payment_method')
        provider_key = None
        if payment_method is not None:
            provider_key = 'cash' if payment_method == 'Cash' else 'stripe'
            provider = get_provider(provider_key)
            if provider is None or not provider.is_enabled():
                return Response(
                    {'detail': _('طريقة الدفع هذه غير متاحة حالياً')},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            total = 0
            order_items_data = []
            item_ids = [item_data['menu_item_id'] for item_data in data['items']]
            menu_items = {
                mi.id: mi
                for mi in MenuItem.objects.filter(
                    id__in=item_ids, restaurant=restaurant, is_available=True,
                )
            }
            for item_data in data['items']:
                mi = menu_items.get(item_data['menu_item_id'])
                if mi is None:
                    return Response(
                        {'detail': f"Menu item {item_data['menu_item_id']} not found or unavailable."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                price = mi.discount_price if mi.discount_price else mi.price
                qty = item_data['quantity']
                total += float(price) * qty
                order_items_data.append({'menu_item': mi, 'quantity': qty, 'price': price})

            pricing = pricing_quote(
                total, restaurant,
                data.get('delivery_lat'), data.get('delivery_lng'),
            )

            order = Order.objects.create(
                customer=request.user,
                customer_name=data.get('customer_name', ''),
                customer_phone=data.get('customer_phone', ''),
                customer_email=data.get('customer_email', request.user.email),
                restaurant=restaurant,
                delivery_address=data['delivery_address'],
                delivery_lat=data.get('delivery_lat'),
                delivery_lng=data.get('delivery_lng'),
                delivery_fee=pricing['delivery_fee'],
                total_price=pricing['total'],
                status='Pending',
            )

            for oi in order_items_data:
                OrderItem.objects.create(order=order, **oi)

            Cart.objects.filter(user=request.user).delete()

        # Deliberately outside the atomic block: the Stripe call is a network
        # round-trip and must not hold a database transaction open. This
        # mirrors the website flow in payments.views.process_payment.
        payment_url = None
        if provider_key is not None:
            try:
                payment = initiate_payment(order, provider_key, request=request)
            except PaymentError as exc:
                logger.error(
                    'Payment initiation failed for order %s: %s', order.id, exc,
                )
                return Response(
                    {'detail': str(exc) or _('تعذر بدء عملية الدفع')},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Cash is marked complete inline by initiate_payment, so the order
            # is already 'Confirmed' by now; only the card path has somewhere
            # to send the customer.
            payment_url = getattr(payment, 'redirect_url', None) or None

        response_data = dict(OrderSerializer(order).data)
        response_data['payment_method'] = payment_method
        response_data['payment_url'] = payment_url
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        valid = [s for s, _ in Order.STATUS_CHOICES]
        if new_status not in valid:
            return Response({'detail': f'Invalid status. Choose from: {valid}'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        self._notify_status_change(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['get'], url_path='tracking')
    def tracking(self, request, pk=None):
        """Live driver position + endpoints for the order tracking screen.

        Access is already scoped by ``get_queryset`` (the order must belong to
        the requesting customer, their restaurant, or they must be admin), so
        ``get_object()`` 404s for anyone else rather than leaking coordinates.
        """
        order = self.get_object()
        return Response(OrderTrackingSerializer(order).data)

    def _notify_status_change(self, order):
        if order.customer is None:
            return
        import threading

        def _send():
            from api.fcm import send_to_user
            title = _('طلبك #%(id)s') % {'id': order.id}
            body = _('حالة طلبك الآن: %(status)s') % {'status': order.status}
            send_to_user(order.customer, title, body, {'order_id': order.id, 'type': 'order_status'})

        threading.Thread(target=_send, daemon=True).start()


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = Review.objects.select_related('user', 'restaurant').all()

    def get_queryset(self):
        qs = self.queryset
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
    from orders.models import Ticket as OT
    queryset = OT.objects.all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return self.queryset.filter(customer=user)
