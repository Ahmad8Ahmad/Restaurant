import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext as _
from django.conf import settings as django_settings
from .models import UserPreference
from .forms import UserPreferenceForm, ProfileForm


@login_required
def settings_view(request):
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    profile_form = ProfileForm(initial={
        'username': request.user.username,
        'email': request.user.email,
        'phone': request.user.phone or '',
        'address': request.user.address or '',
    })
    pref_form = UserPreferenceForm(instance=pref)

    if request.method == 'POST':
        section = request.POST.get('section', 'profile')

        if section == 'profile':
            profile_form = ProfileForm(request.POST)
            if profile_form.is_valid():
                request.user.username = profile_form.cleaned_data['username']
                request.user.phone = profile_form.cleaned_data['phone'] or None
                request.user.address = profile_form.cleaned_data['address'] or None
                request.user.save()
                messages.success(request, _('تم تحديث الملف الشخصي بنجاح'))
                return redirect('user_settings:settings')

        elif section == 'preferences':
            pref_form = UserPreferenceForm(request.POST, instance=pref)
            if pref_form.is_valid():
                pref_form.save()
                messages.success(request, _('تم تحديث التفضيلات بنجاح'))
                return redirect('user_settings:settings')

    ctx = {
        'profile_form': profile_form,
        'pref_form': pref_form,
        'pref': pref,
        'app_version': '1.0.0',
    }
    return render(request, 'user_settings/settings.html', ctx)


@require_POST
@csrf_exempt
def toggle_dark_mode(request):
    """AJAX endpoint to toggle dark mode without page reload."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    data = json.loads(request.body.decode('utf-8')) if request.body else {}
    new_theme = data.get('theme', 'light')
    if new_theme not in ('light', 'dark', 'system'):
        new_theme = 'light'
    pref.theme = new_theme
    pref.save(update_fields=['theme'])
    return JsonResponse({'ok': True, 'theme': pref.theme})


@require_POST
@csrf_exempt
def toggle_notification(request, key):
    """AJAX endpoint to toggle notification preferences."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    valid_keys = {
        'order_updates': 'notify_order_updates',
        'promotions': 'notify_promotions',
        'email': 'notify_email',
    }
    if key not in valid_keys:
        return JsonResponse({'ok': False}, status=400)
    field = valid_keys[key]
    setattr(pref, field, not getattr(pref, field))
    pref.save(update_fields=[field])
    return JsonResponse({'ok': True, key: getattr(pref, field)})
