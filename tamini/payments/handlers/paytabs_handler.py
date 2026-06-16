"""
PayTabs payment handler template.
To activate: create PaymentGateway in admin with code='paytabs', fill config keys.
"""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from .base import PaymentHandler


class PayTabsHandler(PaymentHandler):
    code = 'paytabs'
    name = 'PayTabs'

    def checkout(self, request, order):
        # TODO: Implement PayTabs checkout
        # 1. Send request to PayTabs API to create payment page
        # 2. Store transaction ref in Payment record
        # 3. Redirect user to PayTabs hosted page
        #
        # self.config.get('api_key')  # from admin
        # self.config.get('api_endpoint')
        #
        # Example:
        #   import requests
        #   resp = requests.post(f"{self.config.get('api_endpoint')}/payment/request", json={...})
        #   return redirect(resp.json()['redirect_url'])
        #
        from django.contrib import messages
        messages.error(request, _("بوابة PayTabs غير مفعلة بعد"))
        return redirect('payments:process', order_id=order.id)

    def success(self, request, order):
        # TODO: Verify payment with PayTabs API
        # resp = requests.post(f"{self.config.get('api_endpoint')}/payment/query", json={...})
        # if resp.json()['status'] == 'success':
        #     from .utils import confirm_order
        #     confirm_order(order, 'Card', 'paytabs', transaction_id=...)
        return None

    def cancel(self, request, order):
        from django.contrib import messages
        messages.warning(request, _("تم إلغاء عملية الدفع"))
        return redirect('payments:process', order_id=order.id)

    def webhook(self, request):
        # TODO: Verify signature from PayTabs
        # Update order/payment status
        return JsonResponse({'status': 'ok'})
