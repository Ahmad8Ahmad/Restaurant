from .models import SiteSettings, SUPPORT_AGENT_GROUP


def site_contact_processor(request):
    settings = SiteSettings.get_settings()
    return {
        'SITE_CONTACT_EMAIL': settings['email'],
        'SITE_CONTACT_PHONE': settings['phone'],
        'SITE_WHATSAPP': settings['whatsapp'],
        'SITE_INSTAGRAM': settings['instagram'],
        'SITE_FACEBOOK': settings['facebook'],
        'SITE_X': settings['x'],
        'SITE_SNAPCHAT': settings['snapchat'],
        'SITE_TIKTOK': settings['tiktok'],
    }


def is_support_agent(request):
    user = request.user
    if not user.is_authenticated:
        return {'is_support_agent': False}
    is_agent = (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name=SUPPORT_AGENT_GROUP).exists()
    )
    return {'is_support_agent': is_agent}
