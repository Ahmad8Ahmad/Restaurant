from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from api.serializers import (
    RestaurantListSerializer, RestaurantDetailSerializer,
    CategorySerializer, HeroBannerSerializer, SiteContentSerializer,
)
from api.permissions import IsRestaurantOwner
from restaurants.models import Restaurant, Category, HeroBanner, SiteContent


class RestaurantViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'address']
    ordering_fields = ['created_at', 'name', 'is_trendy']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Restaurant.objects.filter(is_active=True, is_approved=True)
        if self.request.user.is_authenticated and self.request.user.role == 'restaurant':
            qs = Restaurant.objects.filter(owner=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return RestaurantListSerializer
        return RestaurantDetailSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsRestaurantOwner()]

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def menu(self, request, pk=None):
        restaurant = self.get_object()
        from api.serializers import MenuItemSerializer
        items = restaurant.menu_items.filter(is_available=True)
        category_id = request.query_params.get('category')
        if category_id:
            items = items.filter(category_id=category_id)
        return Response(MenuItemSerializer(items, many=True).data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def reviews(self, request, pk=None):
        restaurant = self.get_object()
        from api.serializers import ReviewSerializer
        reviews = restaurant.reviews.select_related('user').all()
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
