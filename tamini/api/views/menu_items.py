from rest_framework import viewsets, permissions, filters
from rest_framework.exceptions import PermissionDenied

from api.serializers import MenuItemSerializer
from api.permissions import IsRestaurantOwnerOrStaff
from restaurants.models import MenuItem, Restaurant


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']

    def _owned_restaurant_id(self):
        user = self.request.user
        if user.role == 'restaurant':
            return Restaurant.objects.filter(owner=user).values_list('id', flat=True).first()
        if user.role == 'staff':
            return user.restaurant_id
        return None

    def get_queryset(self):
        qs = MenuItem.objects.select_related('restaurant', 'category').all()
        if self.action not in ('list', 'retrieve'):
            restaurant_id = self._owned_restaurant_id()
            if restaurant_id is not None:
                qs = qs.filter(restaurant_id=restaurant_id)
        filter_id = self.request.query_params.get('restaurant')
        category_id = self.request.query_params.get('category')
        available = self.request.query_params.get('available')
        if filter_id:
            qs = qs.filter(restaurant_id=filter_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if available is not None:
            qs = qs.filter(is_available=available.lower() in ('true', '1', 'yes'))
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [IsRestaurantOwnerOrStaff()]

    def perform_create(self, serializer):
        restaurant_id = self._owned_restaurant_id()
        if restaurant_id is None:
            raise PermissionDenied('لم يتم ربط مطعم بحسابك بعد')
        serializer.save(restaurant_id=restaurant_id)
