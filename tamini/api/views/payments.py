from rest_framework import viewsets, permissions

from api.serializers import PaymentSerializer, CommissionSerializer
from payments.models import Payment, Commission


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Payment.objects.select_related('order').all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return self.queryset.filter(order__customer=user)


class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Commission.objects.all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return Commission.objects.none()
