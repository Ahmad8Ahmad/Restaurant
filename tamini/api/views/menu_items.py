from rest_framework import viewsets, permissions, filters

from api.serializers import MenuItemSerializer
from restaurants.models import MenuItem


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = MenuItem.objects.select_related('restaurant', 'category').all()
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
        return [permissions.IsAuthenticated()]
