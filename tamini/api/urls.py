from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from api.views.auth import (
    RegisterView, VerifyOTPView, ResendOTPView, LoginView,
    ProfileView, ChangePasswordView, UserListView,
)
from api.views.restaurants import RestaurantViewSet, CategoryViewSet, HeroBannerViewSet, SiteContentView
from api.views.menu_items import MenuItemViewSet
from api.views.cart import CartView, AddToCartView, UpdateCartItemView, RemoveFromCartView, ClearCartView
from api.views.orders import OrderViewSet, ReviewViewSet, OrderTicketViewSet
from api.views.delivery import DeliveryViewSet, DriverProfileViewSet
from api.views.payments import PaymentViewSet, CommissionViewSet
from api.views.support import TicketViewSet, TicketMessageViewSet, site_settings_view

router = DefaultRouter()
router.register(r'restaurants', RestaurantViewSet, basename='restaurant')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'menu-items', MenuItemViewSet, basename='menuitem')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'deliveries', DeliveryViewSet, basename='delivery')
router.register(r'driver-profiles', DriverProfileViewSet, basename='driverprofile')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'commissions', CommissionViewSet, basename='commission')
router.register(r'support-tickets', TicketViewSet, basename='ticket')
router.register(r'banners', HeroBannerViewSet, basename='banner')

urlpatterns = [
    # Auth
    path('auth/register/', RegisterView.as_view(), name='api_register'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='api_verify_otp'),
    path('auth/resend-otp/', ResendOTPView.as_view(), name='api_resend_otp'),
    path('auth/login/', LoginView.as_view(), name='api_login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='api_token_verify'),
    path('auth/profile/', ProfileView.as_view(), name='api_profile'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='api_change_password'),
    path('auth/users/', UserListView.as_view(), name='api_user_list'),

    # Site content
    path('site-content/current/', SiteContentView.as_view({'get': 'current'}), name='api_site_content'),

    # Cart
    path('cart/', CartView.as_view(), name='api_cart'),
    path('cart/add/', AddToCartView.as_view(), name='api_cart_add'),
    path('cart/item/<int:item_id>/', UpdateCartItemView.as_view(), name='api_cart_item'),
    path('cart/item/<int:item_id>/remove/', RemoveFromCartView.as_view(), name='api_cart_item_remove'),
    path('cart/clear/', ClearCartView.as_view(), name='api_cart_clear'),

    # Support
    path('site-settings/', site_settings_view, name='api_site_settings'),

    # Nested ticket messages
    path('support-tickets/<int:ticket_pk>/messages/',
         TicketMessageViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='api_ticket_messages'),

    # Router
    path('', include(router.urls)),
]
