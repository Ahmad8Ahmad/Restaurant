from rest_framework import viewsets, permissions

from api.serializers import PaymentSerializer, CommissionSerializer
from payments.models import Payment, Commission


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return Payment.objects.select_related('order').all()
        return Payment.objects.filter(order__customer=user).select_related('order')


class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return Commission.objects.all()
        return Commission.objects.none()
