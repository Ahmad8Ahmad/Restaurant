from django import forms
from .models import User
from django.contrib.auth.forms import UserCreationForm

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    class Meta:
        model = User
        fields = ['email', 'role', 'phone', 'address']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
      
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = (
                'w-full px-4 py-2 border border-orange-200 rounded-xl '
                'focus:outline-none focus:ring-2 focus:ring-orange-500'
            )