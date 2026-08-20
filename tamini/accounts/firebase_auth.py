import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

logger = logging.getLogger(__name__)
User = get_user_model()


class FirebaseBackend(BaseBackend):
    """
    Authenticate a user that was already verified via Firebase on the
    client side.  The verify view stores the firebase_uid in the session
    so this backend can resolve it on subsequent requests.
    """

    def authenticate(self, request, firebase_uid=None, **kwargs):
        if firebase_uid is None:
            return None
        try:
            return User.objects.get(firebase_uid=firebase_uid)
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
