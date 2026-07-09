from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from tamini.utils import send_mail_async
from django.template.loader import render_to_string
from django.conf import settings
from .models import Ticket, TicketMessage
from .forms import TicketForm, TicketMessageForm
from django.utils.translation import gettext as _


def create_ticket(request):
    if request.method == 'POST':
        form = TicketForm(request.POST, user=request.user if request.user.is_authenticated else None)
        if form.is_valid():
            ticket = form.save(commit=False)
            if request.user.is_authenticated:
                ticket.customer = request.user
            ticket.save()
            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user if request.user.is_authenticated else None,
                author_name=ticket.customer_name,
                message=ticket.description,
            )
            html_msg = render_to_string('support/email_ticket_confirmation.html', {'ticket': ticket})
            send_mail_async(
                _('تذكرة دعم #%(ticket_id)s - تم الاستلام') % {'ticket_id': ticket.id},
                _('تم استلام تذكرتك رقم %(ticket_id)s') % {'ticket_id': ticket.id},
                settings.EMAIL_HOST_USER,
                [ticket.customer_email],
                html_message=html_msg,
            )
            messages.success(request, _('تم إرسال تذكرتك رقم #%(ticket_id)s بنجاح. سنتواصل معك قريباً.') % {'ticket_id': ticket.id})
            return redirect('support:my_tickets' if request.user.is_authenticated else 'home')
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                'customer_name': request.user.username,
                'customer_email': request.user.email,
            }
        form = TicketForm(initial=initial, user=request.user if request.user.is_authenticated else None)
    return render(request, 'support/create_ticket.html', {'form': form})


@login_required
def my_tickets(request):
    tickets = Ticket.objects.filter(customer=request.user).select_related('order')
    return render(request, 'support/my_tickets.html', {'tickets': tickets})


@login_required
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, customer=request.user)
    if request.method == 'POST':
        form = TicketMessageForm(request.POST, request.FILES)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.ticket = ticket
            msg.author = request.user
            msg.author_name = request.user.username
            msg.save()
            if ticket.status == 'closed':
                ticket.status = 'open'
                ticket.save()
            messages.success(request, _('تم إضافة رسالتك.'))
            return redirect('support:ticket_detail', ticket_id=ticket.id)
    else:
        form = TicketMessageForm()
    return render(request, 'support/ticket_detail.html', {'ticket': ticket, 'form': form})


def is_staff(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_staff)
def manage_tickets(request):
    status_filter = request.GET.get('status', '')
    tickets = Ticket.objects.all().select_related('order', 'customer')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    return render(request, 'support/manage_tickets.html', {
        'tickets': tickets,
        'ticket_statuses': Ticket.STATUS_CHOICES,
    })


@login_required
@user_passes_test(is_staff)
def manage_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    if request.method == 'POST':
        if 'status' in request.POST:
            ticket.status = request.POST['status']
            ticket.save()
            messages.success(request, _('تم تحديث حالة التذكرة إلى %(status)s') % {'status': ticket.get_status_display()})
            return redirect('support:manage_ticket_detail', ticket_id=ticket.id)
        form = TicketMessageForm(request.POST, request.FILES)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.ticket = ticket
            msg.author = request.user
            msg.author_name = _('الدعم - %(username)s') % {'username': request.user.username}
            msg.save()
            send_mail_async(
                _('تذكرة دعم #%(ticket_id)s - رد جديد') % {'ticket_id': ticket.id},
                _('هناك رد جديد على تذكرتك.'),
                settings.EMAIL_HOST_USER,
                [ticket.customer_email],
            )
            messages.success(request, _('تم إضافة الرد.'))
            return redirect('support:manage_ticket_detail', ticket_id=ticket.id)
    else:
        form = TicketMessageForm()
    return render(request, 'support/manage_ticket_detail.html', {'ticket': ticket, 'form': form})
