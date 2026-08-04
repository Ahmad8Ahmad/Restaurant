from rest_framework import viewsets, permissions, filters
from rest_framework.exceptions import PermissionDenied

from api.serializers import MenuItemSerializer
from api.permissions import IsRestaurantOwner
from restaurants.models import MenuItem, Restaurant


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = MenuItem.objects.select_related('restaurant', 'category').all()
        if self.request.user.is_authenticated and self.request.user.role == 'restaurant':
            qs = qs.filter(restaurant__owner=self.request.user)
        restaurant_id = self.request.query_params.get('restaurant')
        category_id = self.request.query_params.get('category')
        available = self.request.query_params.get('available')
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if available is not None:
            qs = qs.filter(is_available=available.lower() in ('true', '1', 'yes'))
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [IsRestaurantOwner()]

    def perform_create(self, serializer):
        restaurant = Restaurant.objects.filter(owner=self.request.user).first()
        if restaurant is None:
            raise PermissionDenied('لم يتم ربط مطعم بحسابك بعد')
        serializer.save(restaurant=restaurant)
