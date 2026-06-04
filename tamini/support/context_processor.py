from .models import SiteSettings


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
