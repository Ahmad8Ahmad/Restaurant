# restaurants/forms.py
from django import forms
from .models import Category, MenuItem, Restaurant

class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['category', 'name', 'description', 'price', 'image', 'is_available']
        # إضافة تنسيقات Tailwind للحقول
        widgets = {
            'category': forms.Select(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50'}),
            'name': forms.TextInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'اسم الوجبة'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50'}),
            'image': forms.FileInput(attrs={'class': 'w-full p-2 border rounded-xl bg-gray-50'}),
        }

class CategoryForm(forms.Form):
    class Meta:
        model = Category
        fields = ['name']
        labels = {
            'name': 'اسم التصنيف'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'اسم التصنيف'}),
        }

class RestaurantSettingsForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = ['name', 'phone', 'address', 'latitude', 'longitude', 'logo', 'cover_image', 'is_active']
        labels = {
            'name': 'اسم المطعم',
            'phone': 'رقم الهاتف',
            'address': 'العنوان',
            'latitude': 'خط العرض',
            'longitude': 'خط الطول',
            'logo': 'صورة الشعار',
            'cover_image': 'صورة الخلفية',
            'is_active': 'نشط؟'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'اسم المطعم'}),
            'phone': forms.TextInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'رقم الهاتف'}),
            'address': forms.TextInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'العنوان'}),
            'latitude': forms.NumberInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'مثال: 33.5138', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'w-full p-3 border rounded-xl bg-gray-50', 'placeholder': 'مثال: 36.2765', 'step': 'any'}),
            'logo': forms.FileInput(attrs={'class': 'w-full p-2 border rounded-xl bg-gray-50'}),
            'cover_image': forms.FileInput(attrs={'class': 'w-full p-2 border rounded-xl bg-gray-50'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }