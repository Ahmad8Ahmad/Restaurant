import hashlib
import logging
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django_ratelimit.decorators import ratelimit
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
from tamini.firebase import initialize_firebase

logger = logging.getLogger(__name__)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """Deprecated — registration now uses Firebase only."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        return Response(
            {'detail': 'This registration method is no longer supported. Please use Firebase sign-in.'},
            status=status.HTTP_410_GONE,
        )


class VerifyOTPView(generics.GenericAPIView):
    """Deprecated — verification now uses Firebase only."""
    serializer_class = VerifyOTPSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(
            {'detail': 'OTP verification is no longer supported. Please use Firebase sign-in.'},
            status=status.HTTP_410_GONE,
        )


class ResendOTPView(generics.GenericAPIView):
    """Deprecated — verification now uses Firebase only."""
    serializer_class = ResendOTPSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(
            {'detail': 'OTP verification is no longer supported. Please use Firebase sign-in.'},
            status=status.HTTP_410_GONE,
        )


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

    def _resolve_restaurant(self):
        """Restaurant the staff list/create applies to.

        Owners may pick ``?restaurant=<id>`` (or pass ``restaurant_id``
        on create) if they own several restaurants; otherwise the first
        owned restaurant is used.  Staff are always scoped to their own
        restaurant.
        """
        user = self.request.user
        if user.role == 'staff':
            return Restaurant.objects.filter(id=user.restaurant_id).first()
        qs = Restaurant.objects.filter(owner=user)
        rid = self.request.data.get('restaurant_id') or self.request.query_params.get('restaurant')
        if rid:
            return qs.filter(id=rid).first()
        return qs.first()

    def get_queryset(self):
        user = self.request.user
        base = User.objects.filter(role='staff')
        if user.role == 'staff':
            return base.filter(restaurant_id=user.restaurant_id)
        restaurant = self._resolve_restaurant()
        if restaurant is None:
            return base.none()
        return base.filter(restaurant=restaurant)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return UserSerializer
        return CreateStaffSerializer

    def list(self, request, *args, **kwargs):
        users = self.get_queryset().select_related('restaurant')
        return Response(UserSerializer(users, many=True).data)

    def create(self, request, *args, **kwargs):
        restaurant = self._resolve_restaurant()
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


class SendVerificationEmailView(APIView):
    """POST { "email": "<address>" }

    Asks Firebase to email a verification link to *email*.

    Firebase Admin can generate the action link but cannot send mail itself,
    so the link is delivered through the project's configured email backend.
    The response is deliberately identical for known and unknown addresses so
    this endpoint cannot be used to enumerate registered users, and it is
    IP-rate-limited because it is unauthenticated and sends mail.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'anon'

    # Matches the web resend flow in accounts.views.resend_otp.
    @method_decorator(ratelimit(key='ip', rate='3/m', method='POST'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'detail': 'email is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        initialize_firebase()
        try:
            from firebase_admin import auth as fb_auth
        except ImportError:
            logger.error('firebase_admin is not installed; cannot send verification email.')
            return Response(
                {'detail': 'Could not send a verification email. Please try again later.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            host = request.get_host()
            scheme = 'https' if request.is_secure() else 'http'
            action_code_settings = fb_auth.ActionCodeSettings(
                url=f'{scheme}://{host}/accounts/verification-success/',
                handle_code_in_app=False,
            )
            link = fb_auth.generate_email_verification_link(
                email, action_code_settings=action_code_settings,
            )
        except fb_auth.UserNotFoundError:
            # Unknown address. Answer exactly as we do for a known one so this
            # endpoint cannot be used to discover which emails are registered.
            logger.info('Verification requested for unregistered address %s', email)
            return Response({'detail': 'Verification email sent.'})
        except Exception as exc:
            logger.warning('Verification link failed for %s: %s', email, exc)
            return Response(
                {'detail': 'Could not send a verification email. Please try again later.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            send_mail(
                _('Tamini — verify your email address'),
                _(
                    'Hello,\n\n'
                    'Please confirm your email address to finish setting up '
                    'your Tamini account:\n\n%(link)s\n\n'
                    'If you did not request this, you can ignore this email.'
                ) % {'link': link},
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.error('Verification email delivery failed for %s: %s', email, exc)
            return Response(
                {'detail': 'Could not send a verification email. Please try again later.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'detail': 'Verification email sent.'})


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
