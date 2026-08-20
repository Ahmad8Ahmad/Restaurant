import logging

from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from tamini.firebase import initialize_firebase

logger = logging.getLogger(__name__)
User = get_user_model()


class FirebaseVerifyTokenView(APIView):
    """
    POST { "id_token": "<firebase-id-token>" }

    Verifies the Firebase ID token, gets-or-creates the local User,
    marks them verified, and returns SimpleJWT tokens so the rest of
    the API works as before.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        id_token = request.data.get('id_token', '').strip()
        if not id_token:
            return Response(
                {'detail': 'id_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        initialize_firebase()

        try:
            from firebase_admin import auth as fb_auth
            decoded = fb_auth.verify_id_token(id_token)
        except Exception as exc:
            logger.warning('Firebase token verification failed: %s', exc)
            return Response(
                {'detail': 'Invalid or expired Firebase token.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        firebase_uid = decoded['uid']
        email = decoded.get('email')
        phone = decoded.get('phone_number')
        display_name = decoded.get('name', '')

        if not email and not phone:
            return Response(
                {'detail': 'Firebase token must contain an email or phone number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── get-or-create user ──────────────────────────────────────
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        if user is None and phone:
            user = User.objects.filter(phone=phone).first()
        if user is None:
            import random
            username_base = (email or phone).split('@')[0] if email else f'user_{phone[-4:]}'
            username = f'{username_base}_{random.randint(1000, 9999)}'
            user = User.objects.create_user(
                username=username,
                email=email or f'{firebase_uid}@firebase.local',
                phone=phone or '',
                first_name=display_name,
                is_active=True,
                is_verified=True,
                firebase_uid=firebase_uid,
            )
        else:
            changed = False
            if not user.firebase_uid:
                user.firebase_uid = firebase_uid
                changed = True
            if not user.is_verified:
                user.is_verified = True
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if phone and not user.phone:
                user.phone = phone
                changed = True
            if changed:
                user.save(update_fields=[
                    'firebase_uid', 'is_verified', 'is_active', 'phone',
                ])

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'role': user.role,
                'phone': user.phone,
                'is_verified': user.is_verified,
            },
        }, status=status.HTTP_200_OK)
