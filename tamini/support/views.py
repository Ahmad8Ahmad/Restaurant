from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from tamini.utils import send_mail_async
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Count, OuterRef, Subquery, BooleanField, Value
from django.db.models.functions import Coalesce
from .models import Ticket, TicketMessage, SUPPORT_AGENT_GROUP
from .forms import TicketForm, TicketMessageForm
from django.utils.translation import gettext as _


def _notify_staff():
    """Broadcast a 'tickets_changed' event to the staff channel layer.

    Keeps every open agent console (and the staff live-chat socket) in sync
    when a ticket is claimed, released, or a message is added.  No-op when
    Channels is unavailable.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)('chat_staff', {'type': 'tickets_changed'})
    except Exception:
        pass


def _notify_customer(ticket, message_text, timestamp):
    """Push a support reply straight to the customer's live-chat socket."""
    if not ticket.customer_id:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                f'chat_user_{ticket.customer_id}',
                {
                    'type': 'chat_message',
                    'message': message_text,
                    'author': _('الدعم'),
                    'timestamp': timestamp,
                },
            )
    except Exception:
        pass


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


def is_support_agent(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=SUPPORT_AGENT_GROUP).exists()


def _annotate_tickets(queryset):
    last_msg = TicketMessage.objects.filter(ticket=OuterRef('pk')).order_by('-id')
    return queryset.select_related('customer', 'assignee').annotate(
        msg_count=Count('messages', distinct=True),
        last_author_is_staff=Coalesce(
            Subquery(last_msg.values('author__is_staff')[:1], output_field=BooleanField()),
            Value(False, output_field=BooleanField()),
        ),
    )


@login_required
@user_passes_test(is_support_agent)
def manage_tickets(request):
    view = request.GET.get('view', 'queue')
    status_filter = request.GET.get('status', '')
    is_admin = request.user.is_superuser

    if not is_admin and view not in ('queue', 'mine'):
        view = 'queue'

    if is_admin and view == 'all':
        tickets = Ticket.objects.all()
    elif view == 'mine':
        tickets = Ticket.objects.filter(assignee=request.user)
    else:
        tickets = Ticket.objects.filter(assignee__isnull=True)

    if status_filter:
        tickets = tickets.filter(status=status_filter)

    tickets = _annotate_tickets(tickets).order_by('status', '-updated_at')

    return render(request, 'support/manage_tickets.html', {
        'tickets': tickets,
        'current_view': view,
        'is_admin': is_admin,
        'ticket_statuses': Ticket.STATUS_CHOICES,
        'queue_count': _annotate_tickets(Ticket.objects.filter(assignee__isnull=True)).count(),
        'mine_count': _annotate_tickets(Ticket.objects.filter(assignee=request.user)).count(),
    })


@login_required
@user_passes_test(is_support_agent)
def manage_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(
        Ticket.objects.select_related('customer', 'assignee'),
        id=ticket_id,
    )
    is_admin = request.user.is_superuser
    is_assignee = ticket.assignee_id == request.user.id
    can_act = is_admin or is_assignee

    blocked_by = None
    if ticket.assignee_id and not can_act:
        blocked_by = ticket.assignee

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'claim':
            if not ticket.assignee_id:
                updated = Ticket.objects.filter(pk=ticket.pk, assignee__isnull=True).update(
                    assignee=request.user,
                    status='in_progress',
                )
                if updated:
                    ticket.assignee = request.user
                    ticket.status = 'in_progress'
                    messages.success(request, _('تم استلام التذكرة بنجاح.'))
                    _notify_staff()
                else:
                    messages.error(request, _('استلم وكيل آخر هذه التذكرة للتو.'))
            return redirect('support:manage_ticket_detail', ticket_id=ticket.id)

        if action == 'unclaim':
            if can_act:
                Ticket.objects.filter(pk=ticket.pk).update(assignee=None)
                messages.success(request, _('تمت إعادة التذكرة إلى قائمة الانتظار.'))
                _notify_staff()
            return redirect('support:manage_tickets')

        if blocked_by:
            messages.error(request, _('هذه التذكرة قيد المتابعة من وكيل آخر.'))
            return redirect('support:manage_tickets')

        if 'status' in request.POST and can_act:
            new_status = request.POST['status']
            if ticket.status != new_status:
                ticket.status = new_status
                ticket.save()
                messages.success(request, _('تم تحديث حالة التذكرة إلى %(status)s') % {'status': ticket.get_status_display()})
                _notify_staff()
            return redirect('support:manage_ticket_detail', ticket_id=ticket.id)

        form = TicketMessageForm(request.POST, request.FILES)
        if form.is_valid() and can_act:
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
            _notify_customer(ticket, msg.message, str(msg.created_at))
            _notify_staff()
            messages.success(request, _('تم إضافة الرد.'))
            return redirect('support:manage_ticket_detail', ticket_id=ticket.id)
    else:
        form = TicketMessageForm()

    return render(request, 'support/manage_ticket_detail.html', {
        'ticket': ticket,
        'form': form,
        'is_admin': is_admin,
        'is_assignee': is_assignee,
        'can_act': can_act,
        'blocked_by': blocked_by,
    })