from django.utils.translation import gettext as _
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

    def _owned_restaurants(self):
        """Restaurants the current user may write to.

        Owners may manage every restaurant they own; staff only their
        own restaurant.
        """
        user = self.request.user
        if user.role == 'staff':
            return Restaurant.objects.filter(id=user.restaurant_id)
        return Restaurant.objects.filter(owner=user)

    def get_queryset(self):
        qs = MenuItem.objects.select_related('restaurant', 'category').all()
        if self.action in ('update', 'partial_update', 'destroy'):
            # Scope writes to the user's own restaurants so object-level
            # lookups 404/403 on other owners' menu items.
            owned = self._owned_restaurants()
            total = owned.count()
            if total == 0:
                return qs.none()
            if total == 1:
                qs = qs.filter(restaurant=owned.first())
            else:
                qs = qs.filter(restaurant__in=owned)
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

    def _check_owned_restaurant(self, serializer):
        restaurant = serializer.validated_data.get('restaurant')
        if restaurant is not None:
            owned = self._owned_restaurants()
            if not owned.filter(pk=restaurant.pk).exists():
                raise PermissionDenied(_('لا يمكن إضافة أو نقل وجبة لمطعم لا تملكه'))
        return restaurant

    def perform_create(self, serializer):
        restaurant = self._check_owned_restaurant(serializer)
        if restaurant is None:
            restaurant = self._owned_restaurants().first()
        if restaurant is None:
            raise PermissionDenied(_('لم يتم ربط مطعم بحسابك بعد'))
        serializer.save(restaurant=restaurant)

    def perform_update(self, serializer):
        self._check_owned_restaurant(serializer)
        serializer.save()
