import threading
import logging

logger = logging.getLogger(__name__)


def send_mail_async(subject, text, from_email, recipient_list, html_message=None):
    from django.core.mail import send_mail
    def _send():
        try:
            sent = send_mail(subject, text, from_email, recipient_list, html_message=html_message)
            if not sent:
                logger.warning("send_mail returned False for %s", recipient_list)
        except Exception as e:
            logger.error("send_mail failed for %s: %s", recipient_list, e)
    t = threading.Thread(target=_send, daemon=True)
    t.start()
