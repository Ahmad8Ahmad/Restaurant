from django import forms
from django.utils.translation import gettext_lazy as _
from .models import UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ['theme', 'notify_order_updates', 'notify_promotions', 'notify_email']
        widgets = {
            'theme': forms.RadioSelect,
        }


class ProfileForm(forms.Form):
    username = forms.CharField(
        label=_('Username'),
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 bg-orange-50/60 rounded-xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400 text-sm text-gray-900',
        }),
    )
    email = forms.EmailField(
        label=_('Email'),
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2.5 bg-orange-50/60 rounded-xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400 text-sm text-gray-900',
            'readonly': 'readonly',
        }),
    )
    phone = forms.CharField(
        label=_('Phone'),
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 bg-orange-50/60 rounded-xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400 text-sm text-gray-900',
        }),
    )
    address = forms.CharField(
        label=_('Address'),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2.5 bg-orange-50/60 rounded-xl border border-orange-100 focus:outline-none focus:ring-2 focus:ring-orange-400/40 focus:border-orange-400 text-sm text-gray-900',
            'rows': 2,
        }),
    )
