from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from api.serializers import (
    RestaurantListSerializer, RestaurantDetailSerializer,
    CategorySerializer, HeroBannerSerializer, SiteContentSerializer,
)
from api.permissions import IsRestaurantOwner, IsOwnerOrReadOnly
from restaurants.models import Restaurant, Category, HeroBanner, SiteContent
from django.db.models import Avg


class RestaurantViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'address']
    ordering_fields = ['created_at', 'name', 'is_trendy']
    ordering = ['-created_at']

    def get_queryset(self):
        if self.action in ('update', 'partial_update', 'destroy'):
            # Use the full queryset so object-level ownership checks run
            # (returning 403) instead of a 404 from an owner-scoped filter.
            qs = Restaurant.objects.all()
        elif self.request.user.is_authenticated and self.request.user.role == 'restaurant':
            qs = Restaurant.objects.filter(owner=self.request.user)
        else:
            qs = Restaurant.objects.filter(is_active=True, is_approved=True)
        qs = qs.annotate(average_rating=Avg('reviews__rating'))
        if self.request.query_params.get('trendy', '').lower() in ('true', '1', 'yes'):
            qs = qs.filter(is_trendy=True)
        # RestaurantDetailSerializer exposes categories; load them in one
        # query instead of one per restaurant.
        return qs.prefetch_related('categories')

    def get_serializer_class(self):
        if self.action == 'list':
            return RestaurantListSerializer
        return RestaurantDetailSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsRestaurantOwner(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        if Restaurant.objects.filter(owner=self.request.user).exists():
            raise PermissionDenied('لديك مطعم مسجل بحسابك بالفعل')
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def menu(self, request, pk=None):
        restaurant = self.get_object()
        from api.serializers import MenuItemSerializer
        items = restaurant.menu_items.filter(is_available=True).select_related('restaurant', 'category')
        category_id = request.query_params.get('category')
        if category_id:
            items = items.filter(category_id=category_id)
        return Response(MenuItemSerializer(items, many=True).data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def reviews(self, request, pk=None):
        restaurant = self.get_object()
        from api.serializers import ReviewSerializer
        reviews = restaurant.reviews.select_related('user', 'restaurant').all()
        return Response(ReviewSerializer(reviews, many=True).data)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        if self.request.query_params.get('global', '').lower() in ('true', '1', 'yes'):
            qs = qs.filter(restaurant__isnull=True)
        return qs


class HeroBannerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HeroBanner.objects.filter(is_active=True)
    serializer_class = HeroBannerSerializer
    permission_classes = [permissions.AllowAny]


class SiteContentView(viewsets.ModelViewSet):
    serializer_class = SiteContentSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return SiteContent.objects.all()

    @action(detail=False, methods=['get'])
    def current(self, request):
        content = SiteContent.load()
        return Response(self.get_serializer(content).data)
