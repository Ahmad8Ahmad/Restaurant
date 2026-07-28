from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response

from api.serializers import CartSerializer, CartItemSerializer
from orders.models import Cart, CartItem
from restaurants.models import MenuItem


class AddToCartSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartView(generics.GenericAPIView):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user, session_key=None)
        return Response(CartSerializer(cart).data)


class AddToCartView(generics.GenericAPIView):
    serializer_class = AddToCartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        menu_item_id = serializer.validated_data['menu_item_id']
        quantity = serializer.validated_data['quantity']

        try:
            menu_item = MenuItem.objects.get(id=menu_item_id, is_available=True)
        except MenuItem.DoesNotExist:
            return Response({'detail': 'Menu item not found or unavailable.'}, status=status.HTTP_404_NOT_FOUND)

        cart, _ = Cart.objects.get_or_create(user=request.user, session_key=None)
        item, created = CartItem.objects.get_or_create(cart=cart, menu_item=menu_item)
        if not created:
            item.quantity += quantity
            item.save()
        else:
            item.quantity = quantity
            item.save()

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class UpdateCartItemView(generics.GenericAPIView):
    serializer_class = UpdateCartItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, item_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data['quantity']

        cart, _ = Cart.objects.get_or_create(user=request.user, session_key=None)
        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response({'detail': 'Cart item not found.'}, status=status.HTTP_404_NOT_FOUND)
        item.quantity = quantity
        item.save()
        return Response(CartSerializer(cart).data)


class RemoveFromCartView(generics.GenericAPIView):
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, item_id):
        cart, _ = Cart.objects.get_or_create(user=request.user, session_key=None)
        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
            item.delete()
        except CartItem.DoesNotExist:
            return Response({'detail': 'Cart item not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CartSerializer(cart).data)


class ClearCartView(generics.GenericAPIView):
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user, session_key=None)
        cart.items.all().delete()
        return Response({'detail': 'Cart cleared.'})
