from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Ticket, TicketMessage


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['customer_name', 'customer_email', 'customer_phone', 'order', 'subject', 'description', 'priority']
        base_class = 'w-full px-4 py-2.5 bg-orange-50/60 text-gray-700 rounded-2xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400 transition-all duration-200'
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': base_class, 'placeholder': _('اسمك')}),
            'customer_email': forms.EmailInput(attrs={'class': base_class, 'placeholder': _('بريدك الإلكتروني')}),
            'customer_phone': forms.TextInput(attrs={'class': base_class, 'placeholder': _('رقم هاتفك (اختياري)')}),
            'order': forms.Select(attrs={'class': base_class}),
            'subject': forms.TextInput(attrs={'class': base_class, 'placeholder': _('ملخص المشكلة')}),
            'description': forms.Textarea(attrs={'class': base_class, 'placeholder': _('اشرح المشكلة بالتفصيل...'), 'rows': 5}),
            'priority': forms.Select(attrs={'class': base_class}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields['customer_name'].initial = user.username
            self.fields['customer_email'].initial = user.email
            self.fields['customer_name'].widget.attrs['readonly'] = True
            self.fields['customer_email'].widget.attrs['readonly'] = True
            self.fields['order'].queryset = user.orders.all()


class TicketMessageForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ['message', 'attachment']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-orange-50/60 text-gray-700 rounded-2xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400',
                'placeholder': _('اكتب رسالتك...'),
                'rows': 3,
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-orange-50 file:text-orange-700 hover:file:bg-orange-100',
            }),
        }
