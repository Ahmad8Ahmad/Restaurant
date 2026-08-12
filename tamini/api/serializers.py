import hashlib
import random

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import User
from restaurants.models import Restaurant, MenuItem, Category, HeroBanner, SiteContent
from orders.models import Cart, CartItem, Order, OrderItem, Review, Ticket as OrderTicket
from delivery.models import DriverProfile, Delivery
from payments.models import Payment, Commission
from support.models import SiteSettings, Ticket, TicketMessage


# ── Auth ────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'role', 'phone', 'address', 'is_verified', 'is_approved',
        ]
        read_only_fields = ['id', 'is_verified', 'is_approved']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'password_confirm', 'role', 'phone', 'address']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.is_active = False
        otp = str(random.randint(100000, 999999))
        user.otp_code = hashlib.sha256(otp.encode()).hexdigest()
        user.otp_created_at = timezone.now()
        user.save()
        user._otp_plain = otp
        return user


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class CustomTokenObtainSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = serializers.EmailField()
        self.fields.pop('username', None)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        token['user_id'] = user.id
        return token

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({'email': 'Invalid email or password.'})

        if not user.check_password(password):
            raise serializers.ValidationError({'email': 'Invalid email or password.'})

        if not user.is_active:
            raise serializers.ValidationError({'email': 'Account is not activated.'})

        attrs['username'] = user.email
        data = super().validate(attrs)
        data['user'] = UserSerializer(user).data
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


# ── Restaurants ─────────────────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'image']


class RestaurantListSerializer(serializers.ModelSerializer):
    average_rating = serializers.FloatField(read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            'id', 'name', 'description', 'address', 'latitude', 'longitude',
            'logo', 'cover_image', 'phone', 'is_active', 'is_approved',
            'is_trendy', 'created_at', 'average_rating',
        ]


class RestaurantDetailSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True, source='categories.all')
    average_rating = serializers.FloatField(read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            'id', 'name', 'description', 'address', 'latitude', 'longitude',
            'logo', 'cover_image', 'phone', 'is_active', 'is_approved',
            'is_trendy', 'created_at', 'updated_at', 'categories', 'average_rating',
        ]


class MenuItemSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            'id', 'category', 'category_name', 'restaurant', 'restaurant_name',
            'name', 'description', 'price', 'discount_price', 'image',
            'is_available', 'created_at',
        ]


class HeroBannerSerializer(serializers.ModelSerializer):
    is_video = serializers.BooleanField(read_only=True)

    class Meta:
        model = HeroBanner
        fields = [
            'id', 'title', 'title_size', 'title_color',
            'subtitle', 'subtitle_size', 'subtitle_color',
            'image', 'is_video', 'cta_text', 'cta_url',
            'is_active', 'created_at',
        ]


class SiteContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteContent
        fields = [
            'id', 'welcome_title', 'welcome_title_color', 'welcome_title_size',
            'welcome_subtitle', 'welcome_subtitle_color', 'welcome_subtitle_size',
        ]


# ── Cart ────────────────────────────────────────────────────────────────

class CartItemSerializer(serializers.ModelSerializer):
    menu_item = MenuItemSerializer(read_only=True)
    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.all(), source='menu_item', write_only=True
    )
    subtotal = SerializerMethodField()
    unit_price = SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'menu_item', 'menu_item_id', 'quantity', 'subtotal', 'unit_price']

    def get_subtotal(self, obj) -> float:
        return obj.subtotal()

    def get_unit_price(self, obj) -> float:
        return obj.unit_price()


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = SerializerMethodField()
    total_quantity = SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_price', 'total_quantity', 'created_at']

    def get_total_price(self, obj) -> float:
        # Iterate the (prefetched) items instead of calling obj.total_price(),
        # which would re-query them via select_related()/aggregate().
        return sum(item.subtotal() for item in obj.items.all())

    def get_total_quantity(self, obj) -> int:
        return sum(item.quantity for item in obj.items.all())


# ── Orders ──────────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_name', 'quantity', 'price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    customer_email = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'customer_phone', 'customer_email',
            'restaurant', 'restaurant_name', 'delivery_address',
            'delivery_lat', 'delivery_lng', 'delivery_fee', 'total_price',
            'status', 'customer_order_number', 'items', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'customer', 'total_price', 'customer_order_number', 'created_at']


class OrderCreateSerializer(serializers.Serializer):
    restaurant_id = serializers.PrimaryKeyRelatedField(queryset=Restaurant.objects.all())
    delivery_address = serializers.CharField()
    delivery_lat = serializers.FloatField(required=False, allow_null=True)
    delivery_lng = serializers.FloatField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=255, required=False)
    customer_phone = serializers.CharField(max_length=20, required=False)
    customer_email = serializers.EmailField(required=False)
    items = serializers.ListField(
        child=serializers.DictField(), min_length=1,
        help_text='List of {menu_item_id: int, quantity: int}'
    )

    def validate_items(self, value):
        for item in value:
            if 'menu_item_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError('Each item must have menu_item_id and quantity.')
            if int(item['quantity']) < 1:
                raise serializers.ValidationError('Quantity must be at least 1.')
        return value


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'restaurant', 'restaurant_name', 'user', 'user_email', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class OrderTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderTicket
        fields = ['id', 'code', 'order', 'customer', 'is_active', 'expires_at', 'created_at']
        read_only_fields = ['id', 'code', 'created_at']


# ── Delivery ────────────────────────────────────────────────────────────

class DriverProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = DriverProfile
        fields = ['id', 'user', 'user_email', 'is_approved', 'created_at']
        read_only_fields = ['id', 'created_at']


class DeliverySerializer(serializers.ModelSerializer):
    driver_email = serializers.CharField(source='delivery_person.email', read_only=True)
    restaurant_name = serializers.CharField(source='order.restaurant.name', read_only=True)
    restaurant_address = serializers.CharField(source='order.restaurant.address', read_only=True)
    delivery_address = serializers.CharField(source='order.delivery_address', read_only=True)
    customer_name = serializers.CharField(source='order.customer_name', read_only=True)
    customer_phone = serializers.CharField(source='order.customer_phone', read_only=True)
    order_id_display = serializers.IntegerField(source='order.id', read_only=True)
    distance = SerializerMethodField()
    calculated_fee = SerializerMethodField()

    class Meta:
        model = Delivery
        fields = [
            'id', 'order', 'order_id_display', 'delivery_person', 'driver_email',
            'status', 'current_lat', 'current_lng', 'updated_at',
            'is_settled', 'restaurant_name', 'restaurant_address',
            'delivery_address', 'customer_name', 'customer_phone',
            'distance', 'calculated_fee',
        ]
        read_only_fields = ['id', 'updated_at']

    def get_distance(self, obj) -> float:
        return obj.cached_distance

    def get_calculated_fee(self, obj) -> int:
        return obj.cached_fee


# ── Payments ────────────────────────────────────────────────────────────

class PaymentSerializer(serializers.ModelSerializer):
    order_id_display = serializers.IntegerField(source='order.id', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'order_id_display', 'amount', 'status',
            'transaction_id', 'payment_method', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at']


class CommissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commission
        fields = [
            'id', 'commission_type', 'order', 'delivery', 'amount',
            'is_settled', 'settled_at', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ── Support ─────────────────────────────────────────────────────────────

class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = [
            'id', 'email', 'phone', 'whatsapp', 'instagram', 'facebook',
            'x', 'snapchat', 'tiktok', 'commission_rate',
            'delivery_base_fee', 'delivery_per_km_fee',
            'stripe_publishable_key', 'stripe_currency', 'stripe_exchange_rate',
        ]
        read_only_fields = fields


class TicketMessageSerializer(serializers.ModelSerializer):
    author_name_display = serializers.CharField(source='author.email', read_only=True, default='')

    class Meta:
        model = TicketMessage
        fields = ['id', 'ticket', 'author', 'author_name', 'author_name_display', 'message', 'attachment', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']


class TicketSerializer(serializers.ModelSerializer):
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'customer', 'customer_name', 'customer_email', 'customer_phone',
            'order', 'subject', 'description', 'status', 'priority',
            'created_at', 'updated_at', 'messages',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ['customer_name', 'customer_email', 'customer_phone', 'order', 'subject', 'description']
