from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from api.serializers import PaymentSerializer, CommissionSerializer
from payments.models import Payment, Commission
from payments.providers import enabled_providers


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Payment.objects.select_related('order').all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return self.queryset.filter(order__customer=user)

    @action(detail=False, methods=['get'])
    def methods(self, request):
        return Response([
            {'value': provider.value, 'name': provider.name}
            for provider in enabled_providers()
        ])


class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Commission.objects.all()

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_staff:
            return self.queryset
        return Commission.objects.none()
