# users/services.py
"""Account rules: email changes and email verification."""
import logging

from django.conf import settings
from django.core import signing
from django.template.loader import render_to_string
from django.urls import reverse

from .models import CustomUser

logger = logging.getLogger('nagriksetu.users')

_SALT = 'nagriksetu.email-verification'
VERIFY_MAX_AGE = 3 * 24 * 60 * 60  # three days


def email_in_use(email: str, *, exclude_pk=None) -> bool:
    if not email:
        return False
    qs = CustomUser.objects.filter(email__iexact=email)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def apply_email_change(user: CustomUser, new_email: str) -> bool:
    """Set a new address; it stays unverified until the link is clicked. Returns True if changed."""
    new_email = (new_email or '').strip()
    if new_email.lower() == (user.email or '').lower():
        user.email = new_email
        return False
    user.email = new_email
    user.email_verified = False
    return True


def make_verification_token(user: CustomUser) -> str:
    # Bound to the address, so a link for an old email stops working after a change.
    return signing.dumps({'u': user.pk, 'e': user.email.lower()}, salt=_SALT)


def verify_token(token: str) -> CustomUser | None:
    try:
        payload = signing.loads(token, salt=_SALT, max_age=VERIFY_MAX_AGE)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    user = CustomUser.objects.filter(pk=payload.get('u')).first()
    if not user or (user.email or '').lower() != payload.get('e'):
        return None
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])
    return user


def send_verification_email(request, user: CustomUser) -> None:
    if not user.email or user.email_verified:
        return
    link = request.build_absolute_uri(reverse('verify-email', args=[make_verification_token(user)]))
    body = render_to_string('emails/verify_email.txt', {
        'user': user, 'link': link, 'site_name': settings.SITE_NAME,
    })

    from core.tasks import send_email_task
    try:
        send_email_task.delay(f'[{settings.SITE_NAME}] Confirm your email address', body, [user.email])
    except Exception as exc:  # noqa: BLE001 - never block sign-up on the mail queue
        logger.warning('Could not queue verification email for user %s: %s', user.pk, exc)
