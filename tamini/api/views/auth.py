import hashlib
import random

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from api.serializers import (
    UserSerializer, RegisterSerializer, VerifyOTPSerializer,
    ResendOTPSerializer, CustomTokenObtainSerializer,
    ChangePasswordSerializer, CreateStaffSerializer, FCMTokenSerializer,
)
from api.permissions import IsRestaurantOwner
from restaurants.models import Restaurant
from delivery.models import DriverProfile
from accounts.models import FCMDevice

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        otp_plain = getattr(user, '_otp_plain', None)
        return Response({
            'detail': 'Account created. Please verify your email with the OTP sent.',
            'email': user.email,
            'otp_sent': True,
            'otp_debug': otp_plain,  # Remove in production – useful for testing
        }, status=status.HTTP_201_CREATED)


class VerifyOTPView(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']

        hashed = hashlib.sha256(otp.encode()).hexdigest()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'Invalid email.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.otp_code != hashed:
            return Response({'detail': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.otp_created_at:
            elapsed = (timezone.now() - user.otp_created_at).total_seconds()
            if elapsed > 600:
                return Response({'detail': 'OTP expired. Please register again.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.is_verified = True
        user.otp_code = None
        user.otp_created_at = None
        user.save()

        if user.role == 'restaurant':
            Restaurant.objects.get_or_create(
                owner=user, defaults={'name': f'Restaurant of {user.username}', 'is_approved': False}
            )
        elif user.role == 'delivery':
            DriverProfile.objects.get_or_create(user=user, defaults={'is_approved': False})

        refresh = RefreshToken.for_user(user)
        return Response({
            'detail': 'Account verified successfully.',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class ResendOTPView(generics.GenericAPIView):
    serializer_class = ResendOTPSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        user = User.objects.filter(email=email, is_active=False).first()
        if not user:
            return Response({'detail': 'No pending verification for this email.'}, status=status.HTTP_400_BAD_REQUEST)

        otp = str(random.randint(100000, 999999))
        user.otp_code = hashlib.sha256(otp.encode()).hexdigest()
        user.otp_created_at = timezone.now()
        user.save()

        return Response({
            'detail': 'OTP resent successfully.',
            'otp_debug': otp,  # Remove in production
        }, status=status.HTTP_200_OK)


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'detail': 'Password changed successfully.'})


class UserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()


class StaffListView(generics.ListCreateAPIView):
    """Restaurant owners list & create staff accounts for their restaurant."""

    serializer_class = CreateStaffSerializer
    permission_classes = [IsRestaurantOwner]

    def get_queryset(self):
        return User.objects.filter(
            role='staff', restaurant_id=self.request.user.restaurant_id
        )

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return UserSerializer
        return CreateStaffSerializer

    def list(self, request, *args, **kwargs):
        users = self.get_queryset().select_related('restaurant')
        return Response(UserSerializer(users, many=True).data)

    def create(self, request, *args, **kwargs):
        restaurant = Restaurant.objects.filter(owner=request.user).first()
        if restaurant is None:
            return Response(
                {'detail': 'No restaurant is linked to this account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        staff = serializer.save()
        staff.restaurant = restaurant
        staff.save(update_fields=['restaurant'])
        return Response(
            UserSerializer(staff).data, status=status.HTTP_201_CREATED
        )


class RegisterFCMTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = FCMTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token'].strip()
        if not token:
            return Response({'detail': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        platform = serializer.validated_data.get('platform', '')
        device, _ = FCMDevice.objects.update_or_create(
            user=request.user,
            token=token,
            defaults={'platform': platform},
        )
        return Response({'detail': 'Token registered.', 'id': device.id})

    def delete(self, request):
        token = (request.data.get('token') or '').strip()
        if token:
            FCMDevice.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
