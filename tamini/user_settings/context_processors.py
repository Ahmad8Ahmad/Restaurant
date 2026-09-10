from .models import UserPreference


def user_theme_processor(request):
    theme = ''
    if request.user.is_authenticated:
        pref = getattr(request.user, 'preferences', None)
        if pref is not None:
            theme = pref.theme
        else:
            try:
                theme = UserPreference.get_or_create_for_user(request.user).theme
            except Exception:
                theme = ''
    return {'user_theme': theme}