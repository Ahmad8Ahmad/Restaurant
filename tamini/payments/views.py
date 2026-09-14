from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext as _

from orders.models import Order
from payments import services
from payments.models import Payment
from payments.providers import enabled_providers, get_provider
from payments.providers.base import PaymentError


def process_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    if request.method == 'POST':
        payment_method = (request.POST.get('payment_method') or 'cash').strip().lower()
        try:
            payment = services.initiate_payment(order, payment_method, request=request)
        except PaymentError as exc:
            messages.error(request, str(exc))
            return redirect('payments:process', order_id=order.id)

        redirect_url = getattr(payment, 'redirect_url', None)
        if redirect_url:
            return redirect(redirect_url)

        return render(request, 'payments/success.html', {
            'order': order,
            'payment_method': 'Cash',
        })

    return render(request, 'payments/process.html', {
        'order': order,
        'providers': enabled_providers(),
    })


def create_checkout_session(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    order = get_object_or_404(Order, id=order_id)
    try:
        payment = services.initiate_payment(order, 'stripe', request=request)
    except PaymentError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    redirect_url = getattr(payment, 'redirect_url', None)
    if not redirect_url:
        return JsonResponse({'error': _('الدفع الإلكتروني غير متاح حالياً')}, status=400)
    return JsonResponse({'url': redirect_url})


def stripe_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    payment = Payment.objects.filter(order=order).first()
    provider = get_provider('stripe')
    if provider and payment and payment.transaction_id and payment.status != 'Completed':
        try:
            session = provider.retrieve_session(payment.transaction_id)
            if session is not None and session.payment_status == 'paid':
                services.mark_payment_completed(payment)
        except Exception:
            pass
    return render(request, 'payments/success.html', {
        'order': order,
        'payment_method': 'Card',
    })


def stripe_cancel(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    payment, _created = Payment.objects.update_or_create(
        order=order,
        defaults={'amount': order.total_price},
    )
    services.mark_payment_failed(payment)
    messages.error(request, _("تم إلغاء عملية الدفع. يمكنك المحاولة مرة أخرى."))
    return redirect('orders:view_cart')


@csrf_exempt
def stripe_webhook(request):
    ok = services.process_webhook('stripe', request)
    return HttpResponse(status=200 if ok else 400)